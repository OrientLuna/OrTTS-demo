#import "Demo.h"
#import "StreamPlayback.h"
#import "WorkQueue.h"
#import <sys/sysctl.h>
#import <sys/resource.h>
#ifndef ORTTS_APP_CPU_PROFILE
#define ORTTS_APP_CPU_PROFILE "arm64-baseline"
#endif
#import <AVFoundation/AVFoundation.h>
#import <CommonCrypto/CommonDigest.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#import "ortts_engine.h"

static NSString *const LegacyManifestURL = @"https://modelscope.cn/models/OrientLuna/OrTTS-Qwen3-LFM-0.6B/resolve/v0.2.0-preview/DOWNLOAD_MANIFEST.json";
static NSString *const LiquidManifestURL = @"https://modelscope.cn/models/OrientLuna/OrTTS-Qwen3-LFM-0.6B/resolve/v0.3.1-preview/DOWNLOAD_MANIFEST.json";
static NSString *const BridgeSHA = @"a4202fc2d5ba0352cd847b02e83fd7382b0a2ba54e3e3aefdc4c82c7aa068228";
static BOOL TrustedManifest(NSData *data) {
    if (!data) return NO;
    unsigned char digest[CC_SHA256_DIGEST_LENGTH]; CC_SHA256(data.bytes,(CC_LONG)data.length,digest);
    NSMutableString *hash=[NSMutableString new]; for (int i=0;i<sizeof(digest);i++) [hash appendFormat:@"%02x",digest[i]];
    return [hash isEqual:@"20e24b0bc7fd0e3b58e31dcb409c07102f9e0ddf33f8e70153f69073271b5f7f"] || [hash isEqual:@"2b23c30f658e88ce8b3215e4ea24dacf8898ffca159a7908f61a8942e9e93720"];
}
static NSURL *Documents(void) { return [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject; }
static BOOL Valid(NSURL *url, NSDictionary *entry) {
    NSNumber *size; [url getResourceValue:&size forKey:NSURLFileSizeKey error:nil];
    if (size.unsignedLongLongValue != [entry[@"bytes"] unsignedLongLongValue]) return NO;
    NSInputStream *stream = [NSInputStream inputStreamWithURL:url]; [stream open];
    CC_SHA256_CTX ctx; CC_SHA256_Init(&ctx); uint8_t data[65536]; NSInteger n;
    while ((n = [stream read:data maxLength:sizeof(data)]) > 0) CC_SHA256_Update(&ctx, data, (CC_LONG)n);
    [stream close]; if (n < 0) return NO;
    unsigned char digest[CC_SHA256_DIGEST_LENGTH]; CC_SHA256_Final(digest, &ctx);
    NSMutableString *hash = [NSMutableString new]; for (int i=0;i<sizeof(digest);i++) [hash appendFormat:@"%02x",digest[i]];
    return [hash isEqual:entry[@"sha256"]];
}
@interface Demo () <UIDocumentPickerDelegate, AVAudioPlayerDelegate, UIGestureRecognizerDelegate> {
    NSLock *_lock;
    ortts_engine *_engine;
}
@property UISegmentedControl *variant, *voice, *package;
@property UITextView *text;
@property UILabel *status;
@property UIProgressView *progress;
@property UIButton *download, *synthesize, *stop, *importButton, *replay;
@property AVAudioPlayer *player;
@property StreamPlayback *stream;
- (int)receivePCM:(const float *)pcm count:(size_t)count rate:(int32_t)rate;
@property NSURLSessionDownloadTask *task;
@property BOOL busy, cancelled, legacyPack;
@property BOOL smokeCancelScheduled;
@property NSUInteger smokeSamples;
@end
static int BenchmarkPCM(void *user,const float *pcm,size_t count,int32_t rate){return user&&[(__bridge Demo*)user cancelled]?1:0;}
static int StreamPCM(void *user, const float *pcm, size_t count, int32_t rate) {
    @autoreleasepool { return [(__bridge Demo *)user receivePCM:pcm count:count rate:rate]; }
}
@implementation Demo
- (int)receivePCM:(const float *)pcm count:(size_t)count rate:(int32_t)rate {
    if (self.cancelled || rate!=24000 || count>UINT32_MAX) return 1;
    AVAudioFormat *format=[[AVAudioFormat alloc] initWithCommonFormat:AVAudioPCMFormatFloat32 sampleRate:rate channels:1 interleaved:NO];
    AVAudioPCMBuffer *buffer=[[AVAudioPCMBuffer alloc] initWithPCMFormat:format frameCapacity:(AVAudioFrameCount)count];
    if (!buffer) return 1;
    buffer.frameLength=(AVAudioFrameCount)count; memcpy(buffer.floatChannelData[0],pcm,count*sizeof(float));
    dispatch_async(dispatch_get_main_queue(), ^{ if (!self.cancelled) {
        [self.stream enqueue:buffer]; self.smokeSamples+=buffer.frameLength;
        if ([NSProcessInfo.processInfo.arguments containsObject:@"--cancel-stream-smoke"] && !self.smokeCancelScheduled && self.smokeSamples>=11520) {
            self.smokeCancelScheduled=YES;
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW,100*NSEC_PER_MSEC),dispatch_get_main_queue(), ^{ [self cancel]; });
        }
    } });
    return self.cancelled ? 1:0;
}
- (void)message:(NSString *)message { dispatch_async(dispatch_get_main_queue(), ^{ self.status.text = message; }); }
- (void)setWorking:(BOOL)working {
    self.busy=working;
    for (UIControl *c in @[self.package,self.variant,self.voice,self.download,self.synthesize,self.importButton,self.replay]) c.enabled=!working;
    self.stop.enabled=working || self.player.isPlaying || self.stream.active;
}
- (UIButton *)button:(NSString *)title action:(SEL)action {
    UIButton *b=[UIButton buttonWithType:UIButtonTypeSystem]; [b setTitle:title forState:UIControlStateNormal];
    [b addTarget:self action:action forControlEvents:UIControlEventTouchUpInside]; [b.heightAnchor constraintGreaterThanOrEqualToConstant:44].active=YES; return b;
}
- (void)viewDidLoad {
    [super viewDidLoad]; _lock=[NSLock new]; self.view.backgroundColor=UIColor.systemGroupedBackgroundColor;
    UIScrollView *scroll=[UIScrollView new]; scroll.translatesAutoresizingMaskIntoConstraints=NO; scroll.keyboardDismissMode=UIScrollViewKeyboardDismissModeInteractive; [self.view addSubview:scroll];
    UITapGestureRecognizer *dismiss=[[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(dismissKeyboard)]; dismiss.cancelsTouchesInView=NO; dismiss.delegate=self; [self.view addGestureRecognizer:dismiss];
    UIStackView *stack=[UIStackView new]; stack.axis=UILayoutConstraintAxisVertical; stack.spacing=16; stack.translatesAutoresizingMaskIntoConstraints=NO; [scroll addSubview:stack];
    [NSLayoutConstraint activateConstraints:@[[scroll.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor], [scroll.bottomAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.bottomAnchor], [scroll.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor], [scroll.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor], [stack.topAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.topAnchor constant:24], [stack.bottomAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.bottomAnchor constant:-24], [stack.leadingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.leadingAnchor constant:20], [stack.trailingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.trailingAnchor constant:-20], [stack.widthAnchor constraintEqualToAnchor:scroll.frameLayoutGuide.widthAnchor constant:-40]]];
    UILabel *title=[UILabel new]; title.text=@"OrTTS"; title.font=[UIFont preferredFontForTextStyle:UIFontTextStyleLargeTitle]; [stack addArrangedSubview:title];
    UILabel *subtitle=[UILabel new]; subtitle.text=[NSString stringWithFormat:@"本地语音合成 · CPU · %s",ORTTS_APP_CPU_PROFILE]; subtitle.textColor=UIColor.secondaryLabelColor; [stack addArrangedSubview:subtitle];
    self.package=[[UISegmentedControl alloc] initWithItems:@[@"LiquidCodec · 新版",@"LFM · 旧版兼容"]];self.package.selectedSegmentIndex=0;[self.package addTarget:self action:@selector(packageChanged) forControlEvents:UIControlEventValueChanged];[stack addArrangedSubview:self.package];
    self.variant=[[UISegmentedControl alloc] initWithItems:@[@"P3 · 速度优先",@"P5 · 标准"]]; self.variant.selectedSegmentIndex=0; [stack addArrangedSubview:self.variant];
    self.voice=[[UISegmentedControl alloc] initWithItems:@[@"女声",@"男声"]]; self.voice.selectedSegmentIndex=0; [stack addArrangedSubview:self.voice];
    self.download=[self button:@"下载 / 检查所选模型" action:@selector(downloadModel)]; [stack addArrangedSubview:self.download];
    self.importButton=[self button:@"导入本地模型文件夹" action:@selector(importModel)]; [stack addArrangedSubview:self.importButton];
    self.progress=[UIProgressView new]; [stack addArrangedSubview:self.progress];
    self.text=[UITextView new]; self.text.text=@"你好，欢迎使用 OrTTS。本地语音合成，让交流更加自然。"; self.text.font=[UIFont preferredFontForTextStyle:UIFontTextStyleBody]; self.text.layer.cornerRadius=12;
    UIToolbar *keyboardBar=[UIToolbar new]; [keyboardBar sizeToFit];
    keyboardBar.items=@[[[UIBarButtonItem alloc] initWithBarButtonSystemItem:UIBarButtonSystemItemFlexibleSpace target:nil action:nil], [[UIBarButtonItem alloc] initWithTitle:@"完成" style:UIBarButtonItemStyleDone target:self action:@selector(dismissKeyboard)]];
    self.text.inputAccessoryView=keyboardBar;
     [self.text.heightAnchor constraintEqualToConstant:150].active=YES; [stack addArrangedSubview:self.text];
    self.synthesize=[self button:@"合成并播放" action:@selector(run)]; self.synthesize.configuration=UIButtonConfiguration.filledButtonConfiguration; [self.synthesize setTitle:@"合成并播放" forState:UIControlStateNormal]; [stack addArrangedSubview:self.synthesize];
    self.stop=[self button:@"停止" action:@selector(cancel)]; [stack addArrangedSubview:self.stop];
    self.replay=[self button:@"重播上次音频" action:@selector(play)]; [stack addArrangedSubview:self.replay];
    self.status=[UILabel new]; self.status.numberOfLines=0; self.status.font=[UIFont preferredFontForTextStyle:UIFontTextStyleFootnote]; self.status.text=@"首次使用请下载模型（约 2 GB），保持应用在前台。下载完成后可离线合成。"; [stack addArrangedSubview:self.status]; [self setWorking:NO];
    NSArray *arguments=NSProcessInfo.processInfo.arguments;
    if([arguments containsObject:@"--benchmark-legacy"])self.package.selectedSegmentIndex=1;[self packageChanged];
    NSUInteger textIndex=[arguments indexOfObject:@"--benchmark-text"];
    if (textIndex!=NSNotFound && textIndex+1<arguments.count) self.text.text=arguments[textIndex+1];
    if ([arguments containsObject:@"--benchmark-p5"]) self.variant.selectedSegmentIndex=1;
    if ([arguments containsObject:@"--benchmark-male"]) self.voice.selectedSegmentIndex=self.package.selectedSegmentIndex==0?2:1;
    // Explicit simulator integration-test launch argument; normal launches are idle.
    if ([NSProcessInfo.processInfo.arguments containsObject:@"--download-smoke"]) dispatch_async(dispatch_get_main_queue(), ^{ [self downloadModel]; });
    if([arguments containsObject:@"--benchmark-repeat"]){self.cancelled=NO;[self setWorking:YES];UIApplication.sharedApplication.idleTimerDisabled=YES;NSUInteger delayAt=[arguments indexOfObject:@"--benchmark-cooldown"];NSInteger delay=delayAt!=NSNotFound&&delayAt+1<arguments.count?MIN(180,MAX(0,[arguments[delayAt+1] integerValue])):0;self.status.text=delay?@"等待设备冷却，然后开始对照测试…":self.status.text;dispatch_after(dispatch_time(DISPATCH_TIME_NOW,delay*NSEC_PER_SEC),dispatch_get_main_queue(),^{[self benchmarkOwn];});}
    else if ([NSProcessInfo.processInfo.arguments containsObject:@"--synthesis-smoke"] || [NSProcessInfo.processInfo.arguments containsObject:@"--cancel-stream-smoke"]) dispatch_async(dispatch_get_main_queue(), ^{ [self run]; });
}
- (void)dismissKeyboard { [self.view endEditing:YES]; }
- (void)viewWillDisappear:(BOOL)animated { [super viewWillDisappear:animated]; [self cancel]; }
- (BOOL)gestureRecognizer:(UIGestureRecognizer *)gesture shouldReceiveTouch:(UITouch *)touch {
    // Preserve editing, text selection and scrolling inside the text view.
    for (UIView *view=touch.view; view; view=view.superview) {
        if (view==self.text) return NO;
    }
    return YES;
}
- (NSURL*)modelRoot {return [Documents() URLByAppendingPathComponent:self.legacyPack?@"models":@"models-liquid"];}
- (NSString*)selectedVoice {NSArray*voices=self.package.selectedSegmentIndex==0?@[@"female",@"female_2",@"male",@"male_2"]:@[@"female",@"male"];return voices[MAX(0,MIN(self.voice.selectedSegmentIndex,(NSInteger)voices.count-1))];}
- (void)packageChanged {self.legacyPack=self.package.selectedSegmentIndex==1;[self.stream stop];[self.player stop];[self.voice removeAllSegments];NSArray*names=self.package.selectedSegmentIndex==0?@[@"女声1",@"女声2",@"男声1",@"男声2"]:@[@"女声",@"男声"];for(NSUInteger i=0;i<names.count;i++)[self.voice insertSegmentWithTitle:names[i] atIndex:i animated:NO];self.voice.selectedSegmentIndex=0;self.status.text=self.package.selectedSegmentIndex==0?@"LiquidCodec · v0.3.1 · 独立模型目录，首次下载 P3 约1.81GB":@"旧 LFM · v0.2.0 · 兼容已有模型，性能与新版分别记录";}
- (NSString*)bridgeIdentity:(NSDictionary*)manifest {id runtime=manifest[@"runtime"];NSString*path=[runtime isKindOfClass:NSDictionary.class]?runtime[@"decoder"][@"dequant_manifest"]:nil;if(!path)return BridgeSHA;for(NSDictionary*entry in manifest[@"files"])if([entry[@"path"] isEqual:path])return entry[@"sha256"];return nil;}
- (NSString *)selectedVariant { return self.variant.selectedSegmentIndex==0 ? @"P3":@"P5"; }
- (NSArray *)entries:(NSDictionary *)manifest variant:(NSString *)variant {
    NSMutableArray *result=[NSMutableArray new];
    if (![manifest[@"schema"] isEqual:@"ortts-download-manifest-v1"] || ![manifest[@"files"] isKindOfClass:NSArray.class]) return nil;
    if(![manifest[@"revision"] isEqual:self.legacyPack?@"v0.2.0-preview":@"v0.3.1-preview"])return nil;
    for (NSDictionary *e in manifest[@"files"]) {
        NSString *path=e[@"path"];
        if (![path isKindOfClass:NSString.class] || [path hasPrefix:@"/"] || [path.pathComponents containsObject:@".."] || ![e[@"sha256"] isKindOfClass:NSString.class] || ![e[@"bytes"] isKindOfClass:NSNumber.class]) return nil;
        if ([path hasPrefix:@"native/"] || [path hasPrefix:@"voices/"] || ([variant isEqual:@"P3"] && [path hasPrefix:@"P3/predictor/"])) [result addObject:e];
    }
    return result.count ? result:nil;
}
- (void)finish:(NSString *)message { dispatch_async(dispatch_get_main_queue(), ^{ [self setWorking:NO]; self.status.text=message; NSLog(@"OrTTS status: %@",message); }); }
- (void)downloadModel {
    NSString *variant=[self selectedVariant]; self.cancelled=NO; [self setWorking:YES]; [self message:@"正在获取模型清单…"];
    dispatch_async(OrTTSDemoQueue(), ^{
        NSError *error=nil; NSData *data=[NSData dataWithContentsOfURL:[NSURL URLWithString:self.legacyPack?LegacyManifestURL:LiquidManifestURL] options:0 error:&error];
        NSDictionary *manifest=TrustedManifest(data) ? [NSJSONSerialization JSONObjectWithData:data options:0 error:&error]:nil;
        NSArray *entries=[self entries:manifest variant:variant];
        if (!entries) { [self finish:error.localizedDescription ?: @"模型清单无效"]; return; }
        NSURL *root=[self modelRoot];
        NSUInteger index=0;
        for (NSDictionary *entry in entries) {
            if (self.cancelled) break;
            NSURL *target=[root URLByAppendingPathComponent:entry[@"path"]];
            [self message:[NSString stringWithFormat:@"%lu/%lu 检查 / 下载 %@",(unsigned long)index+1,(unsigned long)entries.count,entry[@"path"]]];
            if (!Valid(target,entry)) {
                [NSFileManager.defaultManager createDirectoryAtURL:target.URLByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:&error];
                dispatch_semaphore_t done=dispatch_semaphore_create(0); __block NSString *failure=nil;
                NSURL *url=[NSURL URLWithString:[manifest[@"base_url"] stringByAppendingString:entry[@"path"]]];
                self.task=[NSURLSession.sharedSession downloadTaskWithURL:url completionHandler:^(NSURL *temp, NSURLResponse *response, NSError *e) {
                    if (e || ((NSHTTPURLResponse *)response).statusCode!=200) failure=e.localizedDescription ?: @"下载失败";
                    else if (!Valid(temp,entry)) failure=@"模型大小或 SHA256 校验失败";
                    else { [NSFileManager.defaultManager removeItemAtURL:target error:nil]; NSError *move=nil; if (![NSFileManager.defaultManager moveItemAtURL:temp toURL:target error:&move]) failure=move.localizedDescription; }
                    dispatch_semaphore_signal(done);
                }]; [self.task resume]; if (self.cancelled) [self.task cancel]; dispatch_semaphore_wait(done,DISPATCH_TIME_FOREVER); self.task=nil;
                if (failure) { [self finish:self.cancelled ? @"下载已停止，可重新检查下载":failure]; return; }
            }
            index++; float fraction=(float)index/entries.count; dispatch_async(dispatch_get_main_queue(), ^{ self.progress.progress=fraction; });
        }
        if (!self.cancelled) [data writeToURL:[root URLByAppendingPathComponent:@"download-manifest.json"] atomically:YES];
        [self finish:self.cancelled ? @"已停止":@"模型已就绪，全部文件校验通过"];
    });
}
- (void)importModel {
    UIDocumentPickerViewController *picker=[[UIDocumentPickerViewController alloc] initForOpeningContentTypes:@[UTTypeFolder] asCopy:NO]; picker.delegate=self; [self presentViewController:picker animated:YES completion:nil];
}
- (void)documentPicker:(UIDocumentPickerViewController *)controller didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls {
    NSURL *source=urls.firstObject; if (!source) return;
    BOOL access=[source startAccessingSecurityScopedResource]; [self setWorking:YES]; self.cancelled=NO;
    [self message:@"正在导入文件夹，随后请点“检查所选模型”完成校验。"];
    dispatch_async(OrTTSDemoQueue(), ^{
        NSURL *root=[self modelRoot]; NSError *error=nil;
        [NSFileManager.defaultManager createDirectoryAtURL:root withIntermediateDirectories:YES attributes:nil error:&error];
        NSData*manifestData=nil;for(NSString*name in @[@"download-manifest.json",@"model.json",@"DOWNLOAD_MANIFEST.json"]){manifestData=[NSData dataWithContentsOfURL:[source URLByAppendingPathComponent:name]];if(manifestData)break;}
        NSDictionary*manifest=TrustedManifest(manifestData)?[NSJSONSerialization JSONObjectWithData:manifestData options:0 error:&error]:nil;NSArray*entries=[self entries:manifest variant:[self selectedVariant]];
        if(!entries)error=[NSError errorWithDomain:@"OrTTS" code:1 userInfo:@{NSLocalizedDescriptionKey:@"清单未通过固定版本校验，或与所选 LiquidCodec/LFM 不匹配。"}];
        for(NSDictionary*entry in entries){if(error||self.cancelled)break;NSURL*from=[source URLByAppendingPathComponent:entry[@"path"]],*to=[root URLByAppendingPathComponent:entry[@"path"]];if(!Valid(from,entry)){error=[NSError errorWithDomain:@"OrTTS" code:1 userInfo:@{NSLocalizedDescriptionKey:@"导入文件 SHA 校验失败"}];break;}if(Valid(to,entry))continue;if([NSFileManager.defaultManager fileExistsAtPath:to.path]){error=[NSError errorWithDomain:@"OrTTS" code:1 userInfo:@{NSLocalizedDescriptionKey:@"目标文件冲突，请先移走所选模型目录。"}];break;}[NSFileManager.defaultManager createDirectoryAtURL:to.URLByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:&error];if(!error)[NSFileManager.defaultManager copyItemAtURL:from toURL:to error:&error];}
        if(!error&&!self.cancelled)[manifestData writeToURL:[root URLByAppendingPathComponent:@"download-manifest.json"] atomically:YES];
        if (access) [source stopAccessingSecurityScopedResource]; [self finish:self.cancelled?@"导入已停止":error.localizedDescription ?: @"导入完成，清单和文件校验通过"];
    });
}
- (void)cancel {
    self.cancelled=YES; [self.task cancel]; [self.player stop]; [self.stream stop];
    [_lock lock]; if (_engine) ortts_engine_cancel(_engine); [_lock unlock];
    self.status.text=self.busy ? @"正在停止生成…":@"播放已停止";
}
- (void)play {
    [self.stream stop];
    NSError *error=nil; [AVAudioSession.sharedInstance setCategory:AVAudioSessionCategoryPlayback mode:AVAudioSessionModeDefault options:0 error:&error]; [AVAudioSession.sharedInstance setActive:YES error:&error];
    self.player=[[AVAudioPlayer alloc] initWithContentsOfURL:[Documents() URLByAppendingPathComponent:@"ortts-output.caf"] error:&error]; self.player.delegate=self;
    if (!self.player || ![self.player play]) self.status.text=error.localizedDescription ?: @"暂无可播放音频";
    self.stop.enabled=self.player.isPlaying;
}
- (void)audioPlayerDidFinishPlaying:(AVAudioPlayer *)player successfully:(BOOL)flag { self.stop.enabled=NO; }
- (void)run {
    if (strcmp(ORTTS_APP_CPU_PROFILE,"arm64-i8mm")==0) {
        int supported=0; size_t size=sizeof(supported);
        if (sysctlbyname("hw.optional.arm.FEAT_I8MM",&supported,&size,NULL,0)!=0 || !supported) {
            self.status.text=@"此优化版本需要 I8MM，请使用 baseline 版本。"; NSLog(@"OrTTS I8MM capability unavailable"); return;
        }
    }
    NSString *text=[self.text.text stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet]; if (!text.length) { self.status.text=@"请输入文字"; return; }
    [self.view endEditing:YES]; [self.player stop]; [self.stream stop]; self.cancelled=NO; [self setWorking:YES];
    NSString *variant=[self selectedVariant], *voice=[self selectedVoice];
    [self message:@"正在校验模型、加载并合成…"];
    dispatch_async(OrTTSDemoQueue(), ^{OrTTSPerformWithStack(^{
        NSURL *root=[self modelRoot];
        NSData *data=[NSData dataWithContentsOfURL:[root URLByAppendingPathComponent:@"download-manifest.json"]];
        NSDictionary *manifest=TrustedManifest(data) ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil]:nil;
        NSArray *entries=[self entries:manifest variant:variant];
        if (!entries) { [self finish:@"请先下载 / 检查所选模型"]; return; }
        for (NSDictionary *entry in entries) { if (self.cancelled || !Valid([root URLByAppendingPathComponent:entry[@"path"]],entry)) { [self finish:self.cancelled ? @"已停止":@"模型校验失败，请重新检查下载"]; return; } }
        NSString *speaker=[[root URLByAppendingPathComponent:[NSString stringWithFormat:@"voices/%@.f32",voice]] path];
        ortts_config c={sizeof(c),root.path.UTF8String,variant.UTF8String,speaker.UTF8String,[self bridgeIdentity:manifest].UTF8String,4,1};
        ortts_engine *engine=NULL; ortts_audio *audio=NULL; int status=ortts_engine_create(&c,&engine);
        if (status) { [self finish:[NSString stringWithUTF8String:ortts_last_error()]]; return; }
        [self->_lock lock]; self->_engine=engine; [self->_lock unlock];
        __block NSError *playbackError=nil;
        dispatch_sync(dispatch_get_main_queue(), ^{
            if(!self.stream)self.stream=[StreamPlayback new];
            if (![self.stream prepare:&playbackError]) return;
            __weak Demo *weakSelf=self;
            self.stream.completion=^{ Demo *s=weakSelf; if (!s.busy) s.stop.enabled=NO; NSLog(@"OrTTS stream drained"); };
            self.status.text=@"正在流式合成播放…";
        });
        ortts_request r={sizeof(r),text.UTF8String,20261029,513};
        if (self.cancelled) status=ORTTS_CANCELLED;
        else if (playbackError) status=ORTTS_RUNTIME_ERROR;
        else status=ortts_engine_synthesize(engine,&r,StreamPCM,(__bridge void *)self,&audio);
        NSString *message=playbackError ? playbackError.localizedDescription : status ? (status==ORTTS_CANCELLED ? @"合成已停止":[NSString stringWithUTF8String:ortts_last_error()]):nil;
        if (!status && !self.cancelled) {
            ortts_metrics metrics; ortts_audio_metrics(audio,&metrics);
            AVAudioFormat *format=[[AVAudioFormat alloc] initWithCommonFormat:AVAudioPCMFormatFloat32 sampleRate:ortts_audio_sample_rate(audio) channels:1 interleaved:NO];
            AVAudioPCMBuffer *buffer=[[AVAudioPCMBuffer alloc] initWithPCMFormat:format frameCapacity:(AVAudioFrameCount)ortts_audio_sample_count(audio)]; buffer.frameLength=buffer.frameCapacity;
            memcpy(buffer.floatChannelData[0],ortts_audio_samples(audio),buffer.frameLength*sizeof(float));
            NSError *error=nil; AVAudioFile *file=[[AVAudioFile alloc] initForWriting:[Documents() URLByAppendingPathComponent:@"ortts-output.caf"] settings:format.settings error:&error];
            if (!file || ![file writeFromBuffer:buffer error:&error]) message=error.localizedDescription ?: @"保存音频失败";
            else { [NSUserDefaults.standardUserDefaults setObject:@"ortts-output.caf" forKey:@"ortts.lastTts"]; double seconds=buffer.frameLength/format.sampleRate; message=[NSString stringWithFormat:@"完成 · 音频 %.2fs · 合成 %.2fs · RTF %.2f",seconds,metrics.api_ms/1000,seconds>0?metrics.api_ms/1000/seconds:0]; }
        }
        BOOL play=!status && !self.cancelled && [message hasPrefix:@"完成"];
        if (self.cancelled) message=@"合成已停止";
        [_lock lock]; self->_engine=NULL; ortts_engine_free(engine); [_lock unlock]; ortts_audio_free(audio);
        dispatch_async(dispatch_get_main_queue(), ^{ [self setWorking:NO]; self.status.text=message; NSLog(@"OrTTS result: %@",message); if (play && !self.cancelled) [self.stream finish]; else [self.stream stop]; });
    });});
}
- (void)benchmarkOwn {
    NSArray*args=NSProcessInfo.processInfo.arguments;NSUInteger at=[args indexOfObject:@"--benchmark-repeat"];NSUInteger count=at!=NSNotFound&&at+1<args.count?MIN((NSUInteger)4,MAX((NSUInteger)1,[args[at+1] integerValue])):4;NSUInteger idAt=[args indexOfObject:@"--benchmark-run-id"];NSString*runID=idAt!=NSNotFound&&idAt+1<args.count?args[idAt+1]:@"own-benchmark";
    NSString*text=[self.text.text copy],*variant=[self selectedVariant],*voiceID=[self selectedVoice];[self setWorking:YES];
    dispatch_async(OrTTSDemoQueue(),^{OrTTSPerformWithStack(^{
        NSURL*root=[self modelRoot];NSData*data=[NSData dataWithContentsOfURL:[root URLByAppendingPathComponent:@"download-manifest.json"]];NSDictionary*manifest=TrustedManifest(data)?[NSJSONSerialization JSONObjectWithData:data options:0 error:nil]:nil;NSArray*entries=[self entries:manifest variant:variant];int status=entries?ORTTS_OK:ORTTS_INVALID;NSString*failure=entries?nil:@"Model manifest missing or untrusted";
        for(NSDictionary*entry in entries)if(self.cancelled)break;else if(!Valid([root URLByAppendingPathComponent:entry[@"path"]],entry)){status=ORTTS_INVALID;failure=@"Model asset SHA validation failed";break;}
        NSString*speaker=[[root URLByAppendingPathComponent:[NSString stringWithFormat:@"voices/%@.f32",voiceID]] path];ortts_config c={sizeof(c),root.path.UTF8String,variant.UTF8String,speaker.UTF8String,[self bridgeIdentity:manifest].UTF8String,4,1};ortts_engine*engine=NULL;NSMutableArray*runs=[NSMutableArray new];
        if(self.cancelled){status=ORTTS_CANCELLED;failure=@"Cancelled";}if(!status){status=ortts_engine_create(&c,&engine);if(status)failure=[NSString stringWithUTF8String:ortts_last_error()];}
        [self->_lock lock];self->_engine=engine;[self->_lock unlock];
        for(NSUInteger i=0;!status&&i<count;i++){@autoreleasepool{
            struct rusage cpuBefore={0},cpuAfter={0};getrusage(RUSAGE_SELF,&cpuBefore);fprintf(stderr,"ORTTS_BENCHMARK_BEGIN %lu\n",(unsigned long)i);ortts_request request={sizeof(request),text.UTF8String,20261029,513};ortts_audio*audio=NULL;status=ortts_engine_synthesize(engine,&request,BenchmarkPCM,(__bridge void*)self,&audio);
            if(status){failure=[NSString stringWithUTF8String:ortts_last_error()];ortts_audio_free(audio);break;}
            ortts_metrics metrics={0};ortts_audio_metrics(audio,&metrics);getrusage(RUSAGE_SELF,&cpuAfter);double cpuMs=(cpuAfter.ru_utime.tv_sec-cpuBefore.ru_utime.tv_sec+cpuAfter.ru_stime.tv_sec-cpuBefore.ru_stime.tv_sec)*1000.0+(cpuAfter.ru_utime.tv_usec-cpuBefore.ru_utime.tv_usec+cpuAfter.ru_stime.tv_usec-cpuBefore.ru_stime.tv_usec)/1000.0;fprintf(stderr,"ORTTS_BENCHMARK_END %lu api_ms=%.6f\n",(unsigned long)i,metrics.api_ms);double seconds=(double)ortts_audio_sample_count(audio)/ortts_audio_sample_rate(audio);
            [runs addObject:@{@"engine_reused":@(i>0),@"ok":@YES,@"api_ms":@(metrics.api_ms),@"audio_s":@(seconds),@"sample_rate":@(ortts_audio_sample_rate(audio)),@"thermal_state":@(NSProcessInfo.processInfo.thermalState),@"low_power_mode":@(NSProcessInfo.processInfo.lowPowerModeEnabled),@"process_cpu_ms":@(cpuMs)}];
            if(i+1==count){AVAudioFormat*format=[[AVAudioFormat alloc]initWithCommonFormat:AVAudioPCMFormatFloat32 sampleRate:ortts_audio_sample_rate(audio) channels:1 interleaved:NO];AVAudioPCMBuffer*buffer=[[AVAudioPCMBuffer alloc]initWithPCMFormat:format frameCapacity:(AVAudioFrameCount)ortts_audio_sample_count(audio)];buffer.frameLength=buffer.frameCapacity;memcpy(buffer.floatChannelData[0],ortts_audio_samples(audio),buffer.frameLength*sizeof(float));NSError*error=nil;AVAudioFile*file=[[AVAudioFile alloc]initForWriting:[Documents() URLByAppendingPathComponent:@"own-benchmark.caf"] settings:format.settings error:&error];if(!file||![file writeFromBuffer:buffer error:&error]){status=ORTTS_RUNTIME_ERROR;failure=error.localizedDescription;}}
            ortts_audio_free(audio);
        }}
        if(self.cancelled){status=ORTTS_CANCELLED;failure=@"Cancelled";}[self->_lock lock];self->_engine=NULL;ortts_engine_free(engine);[self->_lock unlock];NSDictionary*report=@{@"run_id":runID,@"ok":@(!status),@"error":failure ?: @"",@"variant":variant,@"voice":voiceID,@"runs":runs,@"playback":@NO,@"text":text,@"pack":manifest[@"revision"] ?: @"unknown",@"decoder":self.legacyPack?@"qwen_lfm":@"liquidcodec"};NSData*result=[NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:nil];[result writeToURL:[Documents() URLByAppendingPathComponent:@"own-benchmark-result.json"] atomically:YES];dispatch_async(dispatch_get_main_queue(),^{UIApplication.sharedApplication.idleTimerDisabled=NO;[self setWorking:NO];self.status.text=status?failure:@"热启动测试完成";});
    });});
}
@end
