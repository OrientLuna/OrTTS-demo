#import "SpeechDemo.h"
#import "StreamPlayback.h"
#import "WorkQueue.h"
#import "ortts_speech.h"
#import <AVFoundation/AVFoundation.h>
#import <CommonCrypto/CommonDigest.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>

static NSURL *SpeechRoot(void) { return [[NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject URLByAppendingPathComponent:@"speech-models"]; }
static NSError *SpeechError(NSString *message) { return [NSError errorWithDomain:@"OrTTSSpeechDemo" code:1 userInfo:@{NSLocalizedDescriptionKey:message ?: @"操作失败"}]; }
static BOOL SpeechCheck(ortts_status status,NSError **error) { if(status==ORTTS_OK)return YES;if(error)*error=SpeechError(status==ORTTS_CANCELLED?@"已停止":[NSString stringWithUTF8String:ortts_last_error()]);return NO; }
static NSURL *SpeechAsset(NSString *path) {
    if(![path isKindOfClass:NSString.class]||[path hasPrefix:@"/"]||[path containsString:@"\\"]||[path.pathComponents containsObject:@".."])return nil;
    NSURL *file=[SpeechRoot() URLByAppendingPathComponent:path];
    if(![file.URLByResolvingSymlinksInPath.path hasPrefix:[SpeechRoot().URLByResolvingSymlinksInPath.path stringByAppendingString:@"/"]])return nil;
    return file;
}
static BOOL SpeechValid(NSURL *file,NSDictionary *asset,BOOL(^cancel)(void)) {
    NSNumber *bytes=nil;[file getResourceValue:&bytes forKey:NSURLFileSizeKey error:nil];if(!bytes||bytes.unsignedLongLongValue!=[asset[@"bytes"] unsignedLongLongValue])return NO;
    NSInputStream *stream=[NSInputStream inputStreamWithURL:file];[stream open];CC_SHA256_CTX hash;CC_SHA256_Init(&hash);uint8_t buffer[65536];NSInteger n;
    while((n=[stream read:buffer maxLength:sizeof(buffer)])>0){if(cancel()){[stream close];return NO;}CC_SHA256_Update(&hash,buffer,(CC_LONG)n);}[stream close];if(n<0)return NO;
    uint8_t digest[CC_SHA256_DIGEST_LENGTH];CC_SHA256_Final(digest,&hash);NSMutableString *hex=[NSMutableString new];for(int i=0;i<sizeof(digest);i++)[hex appendFormat:@"%02x",digest[i]];return [hex isEqual:asset[@"sha256"]];
}

@interface SpeechDemo () <UIDocumentPickerDelegate,UIGestureRecognizerDelegate> {
    NSLock *_nativeLock,*_captureLock;
    ortts_tts *_tts;ortts_asr *_asr;ortts_asr_stream *_incremental;
    dispatch_semaphore_t _captureSlots;
    NSString *_ttsCacheKey;NSUInteger _ttsEpoch;BOOL _reusedTts;BOOL _benchmarkNoPlayback;NSUInteger _smokeRemaining;NSMutableArray *_smokeRuns;double _lastApiMs,_lastAudioSeconds;
    NSUInteger _frames;NSMutableDictionary<NSNumber*,NSString*> *_finals;
}
@property UISegmentedControl *task;
@property UIStackView *audioActions;
@property UIButton *modelButton,*voiceButton,*downloadButton,*modelImportButton,*primaryButton,*importButton,*lastAudioButton,*stopButton;
@property BOOL importingModels;
@property UILabel *information,*status;
@property UITextView *input,*result;
@property NSArray<NSDictionary*> *catalog;
@property NSDictionary *selected;
@property NSString *voice;
@property BOOL busy,cancelled,recording;
@property NSURLSession *session;
@property NSURLSessionDownloadTask *downloadTask;
@property AVAudioEngine *capture;
@property AVAudioConverter *converter;
@property AVAudioPlayer *player;
@property StreamPlayback *playback;
- (int)receivePCM:(const float*)pcm frames:(size_t)n rate:(int32_t)rate channels:(int32_t)channels;
- (int)receiveText:(const ortts_asr_stream_event*)event;
@end
static int DemoSpeechPCM(void *user,const float*p,size_t n,int32_t rate,int32_t ch){@autoreleasepool{return [(__bridge SpeechDemo*)user receivePCM:p frames:n rate:rate channels:ch];}}
static int DemoSpeechText(void *user,const ortts_asr_stream_event*event){@autoreleasepool{return [(__bridge SpeechDemo*)user receiveText:event];}}

@implementation SpeechDemo
- (UIButton*)button:(NSString*)title action:(SEL)selector {
    UIButton*b=[UIButton buttonWithType:UIButtonTypeSystem];[b setTitle:title forState:UIControlStateNormal];if(selector)[b addTarget:self action:selector forControlEvents:UIControlEventTouchUpInside];NSLayoutConstraint*h=[b.heightAnchor constraintGreaterThanOrEqualToConstant:44];h.priority=999;h.active=YES;return b;
}
- (void)message:(NSString*)value { dispatch_async(dispatch_get_main_queue(),^{self.status.text=value;NSLog(@"SpeechDemo: %@",value);}); }
- (void)working:(BOOL)value {
    self.busy=value;for(UIControl*c in @[self.task,self.modelButton,self.voiceButton,self.downloadButton,self.modelImportButton,self.importButton,self.lastAudioButton])c.enabled=!value;
    self.input.editable=!value;self.primaryButton.enabled=!value||self.recording;
    [self.primaryButton setTitle:self.recording?@"结束录音并识别":self.task.selectedSegmentIndex==0?@"合成并播放":@"开始录音识别" forState:UIControlStateNormal];self.stopButton.enabled=value||self.playback.active;
}
- (void)viewDidLoad {
    [super viewDidLoad];_nativeLock=[NSLock new];_captureLock=[NSLock new];_captureSlots=dispatch_semaphore_create(8);_finals=[NSMutableDictionary new];self.view.backgroundColor=UIColor.systemGroupedBackgroundColor;
    NSURLSessionConfiguration*configuration=NSURLSessionConfiguration.ephemeralSessionConfiguration;configuration.URLCredentialStorage=nil;configuration.HTTPShouldSetCookies=NO;configuration.timeoutIntervalForRequest=30;configuration.timeoutIntervalForResource=1800;self.session=[NSURLSession sessionWithConfiguration:configuration];
    NSData*data=[NSData dataWithContentsOfURL:[NSBundle.mainBundle URLForResource:@"SpeechModels" withExtension:@"json"]];NSDictionary*document=data?[NSJSONSerialization JSONObjectWithData:data options:0 error:nil]:nil;
    self.catalog=[document[@"schema"] isEqual:@"ortts-speech-catalog-v1"]?document[@"models"]:@[];
    UIScrollView*scroll=[UIScrollView new];scroll.translatesAutoresizingMaskIntoConstraints=NO;scroll.keyboardDismissMode=UIScrollViewKeyboardDismissModeInteractive;[self.view addSubview:scroll];UIStackView*stack=[UIStackView new];stack.axis=UILayoutConstraintAxisVertical;stack.spacing=12;stack.translatesAutoresizingMaskIntoConstraints=NO;[scroll addSubview:stack];
    [NSLayoutConstraint activateConstraints:@[[scroll.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor],[scroll.bottomAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.bottomAnchor],[scroll.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],[scroll.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],[stack.topAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.topAnchor constant:20],[stack.bottomAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.bottomAnchor constant:-20],[stack.leadingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.leadingAnchor constant:20],[stack.trailingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.trailingAnchor constant:-20],[stack.widthAnchor constraintEqualToAnchor:scroll.frameLayoutGuide.widthAnchor constant:-40]]];
    UILabel*title=[UILabel new];title.text=@"本地语音 · TTS / ASR";title.font=[UIFont preferredFontForTextStyle:UIFontTextStyleTitle1];[stack addArrangedSubview:title];
    self.task=[[UISegmentedControl alloc]initWithItems:@[@"文字转语音",@"语音转文字"]];self.task.selectedSegmentIndex=self.initialTask;self.task.hidden=YES;[self.task addTarget:self action:@selector(changeTask) forControlEvents:UIControlEventValueChanged];[stack addArrangedSubview:self.task];
    self.modelButton=[self button:@"选择模型" action:nil];self.modelButton.showsMenuAsPrimaryAction=YES;[stack addArrangedSubview:self.modelButton];
    self.voiceButton=[self button:@"选择音色" action:nil];self.voiceButton.showsMenuAsPrimaryAction=YES;[stack addArrangedSubview:self.voiceButton];
    self.information=[UILabel new];self.information.numberOfLines=0;self.information.font=[UIFont preferredFontForTextStyle:UIFontTextStyleFootnote];[stack addArrangedSubview:self.information];
    [stack addArrangedSubview:[self button:@"模型许可与来源" action:@selector(openLicense)]];
    self.downloadButton=[self button:@"下载 / 检查所选模型" action:@selector(downloadModel)];[stack addArrangedSubview:self.downloadButton];
    self.modelImportButton=[self button:@"导入所选模型文件夹" action:@selector(importModels)];[stack addArrangedSubview:self.modelImportButton];
    self.input=[UITextView new];self.input.text=@"Hello, welcome to local speech synthesis.";self.input.font=[UIFont preferredFontForTextStyle:UIFontTextStyleBody];NSLayoutConstraint*inputHeight=[self.input.heightAnchor constraintEqualToConstant:100];inputHeight.priority=999;inputHeight.active=YES;[stack addArrangedSubview:self.input];
    UIToolbar*bar=[UIToolbar new];[bar sizeToFit];bar.items=@[[[UIBarButtonItem alloc]initWithBarButtonSystemItem:UIBarButtonSystemItemFlexibleSpace target:nil action:nil],[[UIBarButtonItem alloc]initWithTitle:@"完成" style:UIBarButtonItemStyleDone target:self action:@selector(dismissKeyboard)]];self.input.inputAccessoryView=bar;
    UITapGestureRecognizer*tap=[[UITapGestureRecognizer alloc]initWithTarget:self action:@selector(dismissKeyboard)];tap.cancelsTouchesInView=NO;tap.delegate=self;[self.view addGestureRecognizer:tap];
    self.primaryButton=[self button:@"合成并播放" action:@selector(primary)];self.primaryButton.configuration=UIButtonConfiguration.filledButtonConfiguration;[stack addArrangedSubview:self.primaryButton];
    self.importButton=[self button:@"导入音频识别（最多60秒）" action:@selector(importAudio)];[stack addArrangedSubview:self.importButton];
    self.lastAudioButton=[self button:@"识别上次合成" action:@selector(recognizeLast)];[stack addArrangedSubview:self.lastAudioButton];
    self.stopButton=[self button:@"取消当前任务" action:@selector(cancel)];[stack addArrangedSubview:self.stopButton];[stack addArrangedSubview:[self button:@"重播上次合成" action:@selector(replay)]];
    self.result=[UITextView new];self.result.editable=NO;self.result.font=[UIFont preferredFontForTextStyle:UIFontTextStyleBody];NSLayoutConstraint*resultHeight=[self.result.heightAnchor constraintEqualToConstant:120];resultHeight.priority=999;resultHeight.active=YES;[stack addArrangedSubview:self.result];
    self.status=[UILabel new];self.status.numberOfLines=0;self.status.font=[UIFont preferredFontForTextStyle:UIFontTextStyleFootnote];[stack addArrangedSubview:self.status];[self changeTask];[self working:NO];
    // Keep the action and recognition result above secondary source/settings.
    for(UIView*v in stack.arrangedSubviews.copy){[stack removeArrangedSubview:v];[v removeFromSuperview];}
    stack.spacing=8;
    UIStackView*selection=[[UIStackView alloc]initWithArrangedSubviews:@[self.modelButton,self.voiceButton]];selection.spacing=8;selection.distribution=UIStackViewDistributionFillProportionally;
    [self.downloadButton setTitle:@"下载 / 检查模型" forState:UIControlStateNormal];[self.modelImportButton setTitle:@"导入模型" forState:UIControlStateNormal];
    UIStackView*models=[[UIStackView alloc]initWithArrangedSubviews:@[self.downloadButton,self.modelImportButton]];models.spacing=8;models.distribution=UIStackViewDistributionFillEqually;
    UIStackView*audio=[[UIStackView alloc]initWithArrangedSubviews:@[self.importButton,self.lastAudioButton]];audio.spacing=8;audio.distribution=UIStackViewDistributionFillEqually;self.audioActions=audio;audio.hidden=self.task.selectedSegmentIndex==0;
    UIStackView*playback=[[UIStackView alloc]initWithArrangedSubviews:@[self.stopButton,[self button:@"重播上次合成" action:@selector(replay)]]];playback.spacing=8;playback.distribution=UIStackViewDistributionFillEqually;
    for(UIView*v in @[title,self.task,selection,self.information,models,self.input,self.primaryButton,audio,self.status,self.result,playback,[self button:@"模型许可与来源" action:@selector(openLicense)]])[stack addArrangedSubview:v];
    self.status.text=@"选择任务和模型，下载一次后可离线使用。录音仅在本机处理。中文合成请使用“自研TTS”页。";
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(interrupted:) name:UIApplicationWillResignActiveNotification object:nil];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(interrupted:) name:AVAudioSessionInterruptionNotification object:nil];
    NSArray*args=NSProcessInfo.processInfo.arguments;_benchmarkNoPlayback=[args containsObject:@"--speech-no-playback"];
    if([args containsObject:@"--speech-smoke"])UIApplication.sharedApplication.idleTimerDisabled=YES;
    if([args containsObject:@"--speech-smoke"])dispatch_async(dispatch_get_main_queue(),^{[self smoke];});
}
- (void)dismissKeyboard{[self.view endEditing:YES];}
- (BOOL)gestureRecognizer:(UIGestureRecognizer*)gesture shouldReceiveTouch:(UITouch*)touch{for(UIView*v=touch.view;v;v=v.superview)if(v==self.input||v==self.result)return NO;return YES;}
- (void)changeTask {
    if(self.busy)return;[self dismissKeyboard];BOOL asr=self.task.selectedSegmentIndex==1;NSMutableArray*actions=[NSMutableArray new];self.selected=nil;
    for(NSDictionary*m in self.catalog)if([m[@"demo_enabled"] boolValue]&&asr==[m[@"task"] isEqual:@"asr"]){if(!self.selected)self.selected=m;[actions addObject:[UIAction actionWithTitle:m[@"display_name"] image:nil identifier:nil handler:^(UIAction*a){if(!self.busy){self.selected=m;[self updateModel];}}]];}
    self.modelButton.menu=[UIMenu menuWithChildren:actions];self.input.hidden=asr;self.voiceButton.hidden=asr;self.importButton.hidden=!asr;self.lastAudioButton.hidden=!asr;self.result.hidden=!asr;self.audioActions.hidden=!asr;[self updateModel];[self working:NO];
}
- (void)updateModel {
    dispatch_async(OrTTSDemoQueue(),^{[self cleanup];});
    NSDictionary*m=self.selected;if(!m){self.status.text=@"模型目录不可用";return;}[self.modelButton setTitle:[m[@"display_name"] stringByAppendingString:@" ▾"] forState:UIControlStateNormal];NSArray*voices=m[@"voice_sample"];self.voice=voices.count?voices.firstObject:nil;NSMutableArray*actions=[NSMutableArray new];
    for(NSString*v in voices)[actions addObject:[UIAction actionWithTitle:v image:nil identifier:nil handler:^(UIAction*a){self.voice=v;[self.voiceButton setTitle:v forState:UIControlStateNormal];}]];
    self.voiceButton.menu=[UIMenu menuWithChildren:actions];[self.voiceButton setTitle:self.voice ?: @"默认" forState:UIControlStateNormal];unsigned long long bytes=0;for(NSDictionary*a in m[@"assets"])bytes+=[a[@"bytes"] unsignedLongLongValue];
    NSString*capability=[m[@"family"] isEqual:@"moonshine_asr"]?@"英文增量识别 · 结果会修订":[m[@"task"] isEqual:@"asr"]?@"中文 / 英文 · 录音结束后输出":@"按模型和音色语言合成";
    self.information.text=[NSString stringWithFormat:@"%@\n约 %.1f MB · %@ · 下载校验",[capability stringByAppendingString:self.task.selectedSegmentIndex==0?@"\n可选 Pocket、Kokoro、Kitten、Piper；按音色语言输入。":@"\n点击模型名称切换：SenseVoice 中文/英语，Moonshine 英语。"],bytes/1e6,m[@"license_review"][@"weights_license"]];
}
- (void)openLicense{
    NSMutableString*text=[NSMutableString stringWithFormat:@"%@\n%@",self.selected[@"license_review"][@"weights_license"],self.selected[@"license_review"][@"source"]];
    [text appendString:@"\n\neSpeak NG 1.52.0: GPL-3.0-or-later\n应用源码与构建说明：https://github.com/OrientLuna/OrTTS-demo\n模型与音色许可另行适用。"];
    for(NSDictionary*voice in self.selected[@"voice_origins"])[text appendFormat:@"\n\n%@ · %@\n%@",voice[@"voice"],voice[@"license"],voice[@"source"]];
    if([self.selected[@"family"] isEqual:@"pocket_tts"])[text appendString:@"\n音色音频已转换为模型嵌入；模型由Kyutai提供。"];
    UIAlertController*alert=[UIAlertController alertControllerWithTitle:@"模型与音色来源" message:text preferredStyle:UIAlertControllerStyleAlert];[alert addAction:[UIAlertAction actionWithTitle:@"关闭" style:UIAlertActionStyleCancel handler:nil]];[alert addAction:[UIAlertAction actionWithTitle:@"打开模型来源" style:UIAlertActionStyleDefault handler:^(UIAlertAction*a){[UIApplication.sharedApplication openURL:[NSURL URLWithString:self.selected[@"license_review"][@"source"]] options:@{} completionHandler:nil];}]];[self presentViewController:alert animated:YES completion:nil];
}
- (void)cleanup {
    ++_ttsEpoch;_ttsCacheKey=nil;[_nativeLock lock];ortts_tts_free(_tts);_tts=NULL;ortts_asr_free(_asr);_asr=NULL;ortts_asr_stream_free(_incremental);_incremental=NULL;[_nativeLock unlock];self.converter=nil;
}
- (void)done:(NSString*)message {dispatch_async(dispatch_get_main_queue(),^{[self working:NO];self.status.text=message ?: @"完成";NSLog(@"SpeechDemo done: %@",self.status.text);
    if([NSProcessInfo.processInfo.arguments containsObject:@"--speech-smoke"]){NSDictionary*report=@{@"run_id":[self argument:@"--speech-run-id" fallback:@"smoke"],@"ok":@([message hasPrefix:@"完成"]||[message hasPrefix:@"识别完成"]||[message hasPrefix:@"模型已就绪"]),@"status":self.status.text,@"text":self.result.text ?: @"",@"model":self.selected[@"id"] ?: @"",@"input_frames":@(self->_frames)};NSMutableDictionary*details=[report mutableCopy];details[@"engine_reused"]=@(self->_reusedTts);details[@"api_ms"]=@(self->_lastApiMs);details[@"audio_s"]=@(self->_lastAudioSeconds);if(self->_smokeRuns){[self->_smokeRuns addObject:details];NSString*scenario=[self argument:@"--speech-scenario" fallback:@""];if(([report[@"ok"] boolValue]||[scenario isEqual:@"cancel"])&&self->_smokeRemaining>1){--self->_smokeRemaining;
if(([scenario isEqual:@"switch"]||[scenario isEqual:@"rate"])){NSString*target=self->_smokeRuns.count==1?([scenario isEqual:@"rate"]?@"piper-lessac-medium":@"pocket-english-q8"):@"kokoro-82m-q8";for(NSDictionary*m in self.catalog)if([m[@"id"] isEqual:target]){self.selected=m;[self updateModel];break;}self.voice=[target isEqual:@"pocket-english-q8"]?@"alba":@"af_heart";}
if([scenario isEqual:@"voice"])self.voice=self->_smokeRuns.count==1?@"am_adam":@"af_heart";
if([scenario isEqual:@"cancel"]&&self->_smokeRuns.count==1)dispatch_after(dispatch_time(DISPATCH_TIME_NOW,100*NSEC_PER_MSEC),dispatch_get_main_queue(),^{[self cancel];});
if([scenario isEqual:@"ttl"])dispatch_after(dispatch_time(DISPATCH_TIME_NOW,31*NSEC_PER_SEC),dispatch_get_main_queue(),^{[self synthesize];});else[self synthesize];return;}}details=[details mutableCopy];details[@"runs"]=[self->_smokeRuns copy] ?: @[];NSData*data=[NSJSONSerialization dataWithJSONObject:details options:NSJSONWritingPrettyPrinted error:nil];UIApplication.sharedApplication.idleTimerDisabled=NO;[data writeToURL:[[NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject URLByAppendingPathComponent:@"speech-smoke-result.json"] atomically:YES];}
});}
- (NSString*)argument:(NSString*)name fallback:(NSString*)fallback{NSArray*a=NSProcessInfo.processInfo.arguments;NSUInteger i=[a indexOfObject:name];return i!=NSNotFound&&i+1<a.count?a[i+1]:fallback;}
- (void)smoke {
    NSString*mode=[self argument:@"--speech-smoke" fallback:@"tts"],*identifier=[self argument:@"--speech-model" fallback:[mode isEqual:@"asr"]?@"moonshine-tiny-q8":@"pocket-english-q8"];
    self.task.selectedSegmentIndex=([mode isEqual:@"asr"]||[mode isEqual:@"last"])?1:0;[self changeTask];for(NSDictionary*m in self.catalog)if([m[@"id"] isEqual:identifier]&&[m[@"demo_enabled"] boolValue]){self.selected=m;[self updateModel];break;}
    if([mode isEqual:@"last"]){[self recognizeLast];return;}
    if([mode isEqual:@"download"]){[self downloadModel];return;}
    if([mode isEqual:@"asr"]){NSString*name=[self argument:@"--speech-audio" fallback:@"speech-test.wav"];NSURL*url=[[NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject URLByAppendingPathComponent:name];[self importURL:url];return;}
    _smokeRemaining=MIN((NSUInteger)4,MAX((NSUInteger)1,(NSUInteger)[[self argument:@"--speech-repeat" fallback:@"1"] integerValue]));_smokeRuns=[NSMutableArray new];self.input.text=[self argument:@"--speech-text" fallback:@"At nine thirty, please check the train ticket and call the station."];self.voice=[self argument:@"--speech-voice" fallback:@"alba"];[self synthesize];NSUInteger delay=[[self argument:@"--speech-cancel-ms" fallback:@"0"] integerValue];if(delay)dispatch_after(dispatch_time(DISPATCH_TIME_NOW,delay*NSEC_PER_MSEC),dispatch_get_main_queue(),^{[self cancel];});
}
- (NSString*)identity:(NSDictionary*)model {
    NSMutableString*value=[NSMutableString stringWithString:model[@"id"]];
    for(NSDictionary*asset in model[@"assets"]){NSDictionary*attrs=[NSFileManager.defaultManager attributesOfItemAtPath:SpeechAsset(asset[@"path"]).path error:nil];[value appendFormat:@"|%@:%@:%@:%0.9f",asset[@"sha256"],attrs[NSFileSystemFileNumber],attrs[NSFileSize],[attrs[NSFileModificationDate] timeIntervalSince1970]];}
    return value;
}
- (BOOL)verify:(NSDictionary*)model error:(NSError**)error {
    for(NSDictionary*a in model[@"assets"])if(!SpeechValid(SpeechAsset(a[@"path"]),a,^BOOL{return self.cancelled;})){if(error)*error=SpeechError(self.cancelled?@"已停止":@"请先下载 / 检查所选模型");return NO;}return YES;
}
- (void)downloadModel {
    if(self.busy)return;[self dismissKeyboard];NSDictionary*model=self.selected;if(!model)return;self.cancelled=NO;[self working:YES];
    dispatch_async(OrTTSDemoQueue(),^{NSError*error=nil;NSUInteger index=0;NSArray*assets=model[@"assets"];
        for(NSDictionary*a in assets){if(self.cancelled)break;NSURL*target=SpeechAsset(a[@"path"]);if(!target){error=SpeechError(@"模型路径无效");break;}[self message:[NSString stringWithFormat:@"%lu/%lu 检查 %@",(unsigned long)++index,(unsigned long)assets.count,target.lastPathComponent]];
            if(SpeechValid(target,a,^BOOL{return self.cancelled;}))continue;
            [NSFileManager.defaultManager createDirectoryAtURL:target.URLByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:&error];if(error)break;
            NSURL*url=[NSURL URLWithString:a[@"url"]];if(![url.scheme isEqual:@"https"]){error=SpeechError(@"模型地址需要HTTPS");break;}dispatch_semaphore_t done=dispatch_semaphore_create(0);__block NSError*failure=nil;
            self.downloadTask=[self.session downloadTaskWithURL:url completionHandler:^(NSURL*temp,NSURLResponse*response,NSError*network){
                if(network)failure=network;else if(((NSHTTPURLResponse*)response).statusCode!=200)failure=SpeechError([NSString stringWithFormat:@"下载HTTP %ld",(long)((NSHTTPURLResponse*)response).statusCode]);
                else if(!SpeechValid(temp,a,^BOOL{return self.cancelled;}))failure=SpeechError(@"模型大小或SHA256不匹配，未安装");
                else if(self.cancelled)failure=SpeechError(@"已停止");
                else if([NSFileManager.defaultManager fileExistsAtPath:target.path]){[NSFileManager.defaultManager replaceItemAtURL:target withItemAtURL:temp backupItemName:nil options:0 resultingItemURL:nil error:&failure];}
                else [NSFileManager.defaultManager moveItemAtURL:temp toURL:target error:&failure];dispatch_semaphore_signal(done);
            }];[self message:[NSString stringWithFormat:@"下载 %@（%.1f MB）",target.lastPathComponent,[a[@"bytes"] doubleValue]/1e6]];[self.downloadTask resume];if(self.cancelled)[self.downloadTask cancel];dispatch_semaphore_wait(done,DISPATCH_TIME_FOREVER);self.downloadTask=nil;if(failure){error=failure;break;}
        }
        [self done:self.cancelled?@"下载已停止，已校验文件会保留":error.localizedDescription ?: @"模型已就绪，大小与SHA256均通过"];
    });
}
- (void)primary {
    if(self.recording){[self stopCapture:NO];return;}if(self.busy)return;[self dismissKeyboard];
    if(self.task.selectedSegmentIndex==0){[self synthesize];return;}
    [AVAudioSession.sharedInstance requestRecordPermission:^(BOOL granted){dispatch_async(dispatch_get_main_queue(),^{if(granted)[self startRecording];else self.status.text=@"未授予麦克风权限；仍可导入音频识别。";});}];
}
- (int)receivePCM:(const float*)pcm frames:(size_t)n rate:(int32_t)rate channels:(int32_t)channels {
    if(_benchmarkNoPlayback)return self.cancelled;
    if(self.cancelled||channels!=1||(rate!=24000&&rate!=22050)||n>UINT32_MAX)return 1;AVAudioFormat*format=[[AVAudioFormat alloc]initWithCommonFormat:AVAudioPCMFormatFloat32 sampleRate:rate channels:1 interleaved:NO];AVAudioPCMBuffer*buffer=[[AVAudioPCMBuffer alloc]initWithPCMFormat:format frameCapacity:(AVAudioFrameCount)n];buffer.frameLength=(AVAudioFrameCount)n;memcpy(buffer.floatChannelData[0],pcm,n*sizeof(float));dispatch_async(dispatch_get_main_queue(),^{if(!self.cancelled)[self.playback enqueue:buffer];});return self.cancelled;
}
- (void)synthesize {
    NSString*text=[self.input.text stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];if(!text.length||text.length>500){self.status.text=@"请输入1–500字符；Kokoro 中文音色支持中文。";return;}
    NSDictionary*model=self.selected;NSString*voice=self.voice;[self.voiceButton setTitle:voice ?: @"默认" forState:UIControlStateNormal];self.cancelled=NO;[self.player stop];[self.playback stop];[self working:YES];[self message:@"正在校验并加载模型…"];
    dispatch_async(OrTTSDemoQueue(),^{OrTTSPerformWithStack(^{NSError*error=nil;ortts_speech_audio*audio=NULL;
        ortts_speech_config c={0};c.struct_size=sizeof(c);c.family=[model[@"family"] UTF8String];c.model_path=SpeechAsset(model[@"model_path"]).path.UTF8String;c.threads=4;c.streaming=![model[@"family"] isEqual:@"piper_tts"]&&![model[@"family"] isEqual:@"kitten_tts"];NSString*g2p=[NSBundle.mainBundle pathForResource:@"espeak-ng" ofType:@"framework" inDirectory:@"Frameworks"];NSString*lib=[g2p stringByAppendingPathComponent:@"espeak-ng"];NSString*data=[NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"espeak-ng-data"];if([model[@"external_espeak"] boolValue]){c.espeak_library=lib.UTF8String;c.espeak_data=data.UTF8String;}
        NSString*key=[NSString stringWithFormat:@"%@|%@|%d",model[@"id"],[self identity:model],c.streaming];self->_reusedTts=self->_tts&&[self->_ttsCacheKey isEqual:key];++self->_ttsEpoch;
        if(!self->_reusedTts){[self cleanup];if(![self verify:model error:&error]){[self done:error.localizedDescription];return;}ortts_tts*created=NULL;if(!SpeechCheck(ortts_tts_create(&c,&created),&error)){[self done:error.localizedDescription];return;}[self->_nativeLock lock];self->_tts=created;self->_ttsCacheKey=key;[self->_nativeLock unlock];}ortts_tts*engine=self->_tts;
        __block NSError*playError=nil;dispatch_sync(dispatch_get_main_queue(),^{if(self->_benchmarkNoPlayback)return;if(!self.playback)self.playback=[StreamPlayback new];__weak SpeechDemo*weakSelf=self;self.playback.completion=^{weakSelf.stopButton.enabled=weakSelf.busy;};[self.playback prepareRate:[model[@"family"] isEqual:@"piper_tts"]?22050:24000 error:&playError];});
        ortts_tts_request r={0};r.struct_size=sizeof(r);r.text=text.UTF8String;r.language=[voice hasPrefix:@"z"]?"zh":"en";r.voice_id=[model[@"family"] isEqual:@"piper_tts"]?NULL:voice.UTF8String;r.seed_set=1;r.seed=42;
        if(self.cancelled)error=SpeechError(@"已停止");else if(playError)error=playError;else SpeechCheck(ortts_tts_synthesize(engine,&r,c.streaming?DemoSpeechPCM:NULL,(__bridge void*)self,&audio),&error);
        NSString*summary=nil;self->_lastApiMs=0;self->_lastAudioSeconds=0;if(!error&&audio){if(!c.streaming)DemoSpeechPCM((__bridge void*)self,ortts_speech_audio_samples(audio),ortts_speech_audio_frames(audio),ortts_speech_audio_sample_rate(audio),1);int rate=ortts_speech_audio_sample_rate(audio);size_t n=ortts_speech_audio_frames(audio);ortts_metrics metrics={0};ortts_speech_audio_metrics(audio,&metrics);self->_lastApiMs=metrics.api_ms;self->_lastAudioSeconds=(double)n/rate;AVAudioFormat*format=[[AVAudioFormat alloc]initWithCommonFormat:AVAudioPCMFormatFloat32 sampleRate:rate channels:1 interleaved:NO];AVAudioPCMBuffer*buffer=[[AVAudioPCMBuffer alloc]initWithPCMFormat:format frameCapacity:(AVAudioFrameCount)n];buffer.frameLength=(AVAudioFrameCount)n;memcpy(buffer.floatChannelData[0],ortts_speech_audio_samples(audio),n*sizeof(float));NSURL*file=[[NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject URLByAppendingPathComponent:@"speech-last.caf"];AVAudioFile*output=[[AVAudioFile alloc]initForWriting:file settings:format.settings error:&error];if(output)[output writeFromBuffer:buffer error:&error];if(!error)[NSUserDefaults.standardUserDefaults setObject:@"speech-last.caf" forKey:@"ortts.lastTts"];summary=[NSString stringWithFormat:@"完成 · %.2fs · 接口RTF %.3f · %@",(double)n/rate,metrics.api_ms/(1000.0*n/rate),self->_reusedTts?@"复用引擎":@"首次构图"];}
        ortts_speech_audio_free(audio);if(error||self.cancelled)[self cleanup];else{NSUInteger ticket=self->_ttsEpoch;dispatch_after(dispatch_time(DISPATCH_TIME_NOW,30*NSEC_PER_SEC),OrTTSDemoQueue(),^{if(self->_ttsEpoch==ticket)[self cleanup];});}dispatch_async(dispatch_get_main_queue(),^{if(!error&&!self.cancelled)[self.playback finish];else[self.playback stop];});[self done:self.cancelled?@"已停止":error.localizedDescription ?: summary];
    });});
}
- (BOOL)openASR:(NSDictionary*)model error:(NSError**)error {
    [self cleanup];
    if(![self verify:model error:error])return NO;ortts_speech_config c={0};c.struct_size=sizeof(c);c.family=[model[@"family"] UTF8String];c.model_path=SpeechAsset(model[@"model_path"]).path.UTF8String;c.threads=4;BOOL incremental=[model[@"family"] isEqual:@"moonshine_asr"];c.streaming=incremental;
    ortts_asr*offline=NULL;ortts_asr_stream*stream=NULL;BOOL ok=SpeechCheck(incremental?ortts_asr_stream_create(&c,NULL,&stream):ortts_asr_create(&c,&offline),error);if(!ok)return NO;
    [_nativeLock lock];_asr=offline;_incremental=stream;[_nativeLock unlock];_frames=0;[_finals removeAllObjects];dispatch_async(dispatch_get_main_queue(),^{self.result.text=@"";});return YES;
}
- (int)receiveText:(const ortts_asr_stream_event*)event {
    if(self.cancelled)return 1;NSString*text=[NSString stringWithUTF8String:event->text] ?: @"";if(event->endpoint&&text.length)_finals[@(event->segment_id)]=text;NSMutableArray*lines=[NSMutableArray new];for(NSNumber*key in [[_finals allKeys] sortedArrayUsingSelector:@selector(compare:)])[lines addObject:_finals[key]];if(!event->endpoint&&text.length)[lines addObject:[@"识别中：" stringByAppendingString:text]];NSString*value=[lines componentsJoinedByString:@"\n"];dispatch_async(dispatch_get_main_queue(),^{self.result.text=value;});return self.cancelled;
}
- (BOOL)acceptPCM:(const float*)pcm count:(NSUInteger)n error:(NSError**)error {
    n=MIN(n,960000-_frames);for(NSUInteger at=0;at<n;at+=1600){NSUInteger take=MIN((NSUInteger)1600,n-at);if(self.cancelled){if(error)*error=SpeechError(@"已停止");return NO;}if(!SpeechCheck(_incremental?ortts_asr_stream_accept(_incremental,pcm+at,take,DemoSpeechText,(__bridge void*)self):ortts_asr_accept(_asr,pcm+at,take),error))return NO;_frames+=take;}return YES;
}
- (BOOL)convert:(AVAudioPCMBuffer*)buffer ending:(BOOL)ending error:(NSError**)error {
    if(!self.converter)return YES;AVAudioFormat*target=self.converter.outputFormat;AVAudioFrameCount capacity=buffer?(AVAudioFrameCount)ceil(buffer.frameLength*16000.0/buffer.format.sampleRate)+128:512;AVAudioPCMBuffer*output=[[AVAudioPCMBuffer alloc]initWithPCMFormat:target frameCapacity:capacity];__block BOOL consumed=NO;
    AVAudioConverterOutputStatus status=[self.converter convertToBuffer:output error:error withInputFromBlock:^AVAudioBuffer*(AVAudioPacketCount count,AVAudioConverterInputStatus*state){if(ending){*state=AVAudioConverterInputStatus_EndOfStream;return nil;}if(consumed){*state=AVAudioConverterInputStatus_NoDataNow;return nil;}consumed=YES;*state=AVAudioConverterInputStatus_HaveData;return buffer;}];
    if(status==AVAudioConverterOutputStatus_Error)return NO;return output.frameLength?[self acceptPCM:output.floatChannelData[0] count:output.frameLength error:error]:YES;
}
- (void)finishASR {
    NSError*error=nil;if(!self.cancelled&&_frames){[self convert:nil ending:YES error:&error];if(!error){if(_incremental)SpeechCheck(ortts_asr_stream_finish(_incremental,DemoSpeechText,(__bridge void*)self),&error);else{ortts_transcript*result=NULL;if(SpeechCheck(ortts_asr_finish(_asr,NULL,&result),&error)){ortts_asr_stream_event e={sizeof(e),ORTTS_ASR_FLUSH,0,0,_frames,1,ortts_transcript_text(result),"auto"};[self receiveText:&e];ortts_transcript_free(result);}}}}
    NSString*message=self.cancelled?@"已取消":(error.localizedDescription ?: (_frames?[NSString stringWithFormat:@"识别完成 · 输入 %.2fs",_frames/16000.0]:@"未录到有效音频"));[self cleanup];dispatch_async(dispatch_get_main_queue(),^{[AVAudioSession.sharedInstance setActive:NO withOptions:AVAudioSessionSetActiveOptionNotifyOthersOnDeactivation error:nil];});[self done:message];
}
- (void)startRecording {
    if(self.busy)return;NSDictionary*model=self.selected;self.cancelled=NO;[self.player stop];[self.playback stop];[self working:YES];[self message:@"正在校验并加载识别模型…"];
    dispatch_async(OrTTSDemoQueue(),^{NSError*error=nil;if(![self openASR:model error:&error]){[self done:error.localizedDescription];return;}
        dispatch_async(dispatch_get_main_queue(),^{if(self.cancelled){dispatch_async(OrTTSDemoQueue(),^{[self cleanup];[self done:@"已停止"];});return;}NSError*error=nil;[AVAudioSession.sharedInstance setCategory:AVAudioSessionCategoryRecord mode:AVAudioSessionModeMeasurement options:0 error:&error];if(!error)[AVAudioSession.sharedInstance setActive:YES error:&error];
            self.capture=[AVAudioEngine new];AVAudioInputNode*node=self.capture.inputNode;AVAudioFormat*format=[node outputFormatForBus:0];AVAudioFormat*target=[[AVAudioFormat alloc]initWithCommonFormat:AVAudioPCMFormatFloat32 sampleRate:16000 channels:1 interleaved:NO];if(format.sampleRate<=0||format.channelCount<1||format.commonFormat!=AVAudioPCMFormatFloat32||format.interleaved)error=SpeechError(@"Unsupported microphone format");
            self.converter=error?nil:[[AVAudioConverter alloc]initFromFormat:format toFormat:target];if(!self.converter&&!error)error=SpeechError(@"麦克风格式不支持");
            if(error){dispatch_async(OrTTSDemoQueue(),^{[self cleanup];[self done:error.localizedDescription];});return;}
            [self->_captureLock lock];self.recording=YES;[self->_captureLock unlock];
            [node installTapOnBus:0 bufferSize:1024 format:format block:^(AVAudioPCMBuffer*buffer,AVAudioTime*time){
                [self->_captureLock lock];if(!self.recording){[self->_captureLock unlock];return;}
                if(dispatch_semaphore_wait(self->_captureSlots,DISPATCH_TIME_NOW)!=0){[self->_captureLock unlock];dispatch_async(dispatch_get_main_queue(),^{[self message:@"设备处理速度不足，录音已停止；可导入文件识别。"];[self stopCapture:YES];});return;}
                AVAudioPCMBuffer*copy=[[AVAudioPCMBuffer alloc]initWithPCMFormat:buffer.format frameCapacity:buffer.frameLength];copy.frameLength=buffer.frameLength;
                for(AVAudioChannelCount ch=0;ch<buffer.format.channelCount;ch++)memcpy(copy.floatChannelData[ch],buffer.floatChannelData[ch],buffer.frameLength*sizeof(float));
                dispatch_async(OrTTSDemoQueue(),^{NSError*failure=nil;if(!self.cancelled&&![self convert:copy ending:NO error:&failure]){self.cancelled=YES;[self message:failure.localizedDescription];dispatch_async(dispatch_get_main_queue(),^{[self stopCapture:YES];});}dispatch_semaphore_signal(self->_captureSlots);if(self->_frames>=960000)dispatch_async(dispatch_get_main_queue(),^{[self stopCapture:NO];});});[self->_captureLock unlock];
            }];[self.capture prepare];if(![self.capture startAndReturnError:&error]){[self stopCapture:YES];[self message:error.localizedDescription];return;}[self working:YES];self.status.text=@"正在录音 · 最长60秒；再次点击结束识别";
        });
    });
}
- (void)stopCapture:(BOOL)cancel {
    [_captureLock lock];BOOL wasRecording=self.recording;self.recording=NO;[_captureLock unlock];if(cancel)self.cancelled=YES;if(!wasRecording)return;
    [self.capture stop];[self.capture.inputNode removeTapOnBus:0];self.capture=nil;self.primaryButton.enabled=NO;[self message:@"正在完成识别…"];dispatch_async(OrTTSDemoQueue(),^{[self finishASR];});
}
- (void)importAudio {if(self.busy)return;UIDocumentPickerViewController*picker=[[UIDocumentPickerViewController alloc]initForOpeningContentTypes:@[UTTypeAudio] asCopy:NO];picker.delegate=self;[self presentViewController:picker animated:YES completion:nil];}
- (void)importModels{if(self.busy)return;self.importingModels=YES;UIDocumentPickerViewController*picker=[[UIDocumentPickerViewController alloc]initForOpeningContentTypes:@[UTTypeFolder] asCopy:NO];picker.delegate=self;[self presentViewController:picker animated:YES completion:nil];}
- (void)recognizeLast {
    if(self.busy)return;NSURL*documents=[NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;NSURL*chosen=nil;NSDate*newest=nil;
    NSString*saved=[NSUserDefaults.standardUserDefaults stringForKey:@"ortts.lastTts"];if([@[@"speech-last.caf",@"ortts-output.caf"] containsObject:saved]){NSURL*file=[documents URLByAppendingPathComponent:saved];if([NSFileManager.defaultManager fileExistsAtPath:file.path]){[self importURL:file];return;}}
    for(NSString*name in @[@"speech-last.caf",@"ortts-output.caf"]){NSURL*file=[documents URLByAppendingPathComponent:name];NSDate*date=nil;[file getResourceValue:&date forKey:NSURLContentModificationDateKey error:nil];if(date&&(!newest||[date compare:newest]==NSOrderedDescending)){newest=date;chosen=file;}}
    if(chosen)[self importURL:chosen];else self.status.text=@"请先合成一条音频。";
}
- (void)documentPicker:(UIDocumentPickerViewController*)controller didPickDocumentsAtURLs:(NSArray<NSURL*>*)urls {
    if(self.importingModels){self.importingModels=NO;[self importModelsURL:urls.firstObject];}else[self importURL:urls.firstObject];
}
- (void)documentPickerWasCancelled:(UIDocumentPickerViewController*)controller{self.importingModels=NO;}
- (void)importModelsURL:(NSURL*)folder {
    if(!folder||self.busy)return;NSDictionary*model=self.selected;BOOL access=[folder startAccessingSecurityScopedResource];self.cancelled=NO;[self working:YES];
    dispatch_async(OrTTSDemoQueue(),^{NSError*error=nil;NSString*base=[model[@"model_path"] stringByDeletingLastPathComponent];
        for(NSDictionary*asset in model[@"assets"]){if(self.cancelled)break;NSURL*target=SpeechAsset(asset[@"path"]);if(SpeechValid(target,asset,^BOOL{return self.cancelled;}))continue;
            NSURL*source=[folder URLByAppendingPathComponent:asset[@"path"]];if(![NSFileManager.defaultManager fileExistsAtPath:source.path]){NSString*relative=asset[@"path"];if(base.length&&[relative hasPrefix:[base stringByAppendingString:@"/"]])relative=[relative substringFromIndex:base.length+1];source=[folder URLByAppendingPathComponent:relative];}
            if(!SpeechValid(source,asset,^BOOL{return self.cancelled;})){error=SpeechError(@"导入文件缺失、大小或SHA256不匹配；请保留模型目录结构。");break;}
            [NSFileManager.defaultManager createDirectoryAtURL:target.URLByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:&error];if(error)break;
            NSURL*partial=[target.URLByDeletingLastPathComponent URLByAppendingPathComponent:[NSUUID.UUID.UUIDString stringByAppendingString:@".part"]];
            if(![NSFileManager.defaultManager copyItemAtURL:source toURL:partial error:&error])break;
            if(!SpeechValid(partial,asset,^BOOL{return self.cancelled;})){[NSFileManager.defaultManager removeItemAtURL:partial error:nil];error=SpeechError(@"导入文件校验失败");break;}
            if([NSFileManager.defaultManager fileExistsAtPath:target.path])[NSFileManager.defaultManager replaceItemAtURL:target withItemAtURL:partial backupItemName:nil options:0 resultingItemURL:nil error:&error];else[NSFileManager.defaultManager moveItemAtURL:partial toURL:target error:&error];if(error){[NSFileManager.defaultManager removeItemAtURL:partial error:nil];break;}
        }if(access)[folder stopAccessingSecurityScopedResource];[self done:self.cancelled?@"导入已停止":error.localizedDescription ?: @"模型已就绪，导入文件SHA256通过"];
    });
}
- (void)importURL:(NSURL*)url {
    if(!url||self.busy)return;NSDictionary*model=self.selected;self.cancelled=NO;[self working:YES];BOOL scoped=[url startAccessingSecurityScopedResource];
    dispatch_async(OrTTSDemoQueue(),^{NSError*error=nil;if(![self openASR:model error:&error]){if(scoped)[url stopAccessingSecurityScopedResource];[self done:error.localizedDescription];return;}
        AVAudioFile*file=[[AVAudioFile alloc]initForReading:url commonFormat:AVAudioPCMFormatFloat32 interleaved:NO error:&error];if(file&&(file.processingFormat.sampleRate<8000||file.processingFormat.sampleRate>192000||file.length/file.processingFormat.sampleRate>60))error=SpeechError(@"请选择8–192kHz、最多60秒的音频");
        if(file&&!error){AVAudioFormat*target=[[AVAudioFormat alloc]initWithCommonFormat:AVAudioPCMFormatFloat32 sampleRate:16000 channels:1 interleaved:NO];self.converter=[[AVAudioConverter alloc]initFromFormat:file.processingFormat toFormat:target];if(!self.converter)error=SpeechError(@"音频格式无法转换");while(!error&&!self.cancelled&&_frames<960000&&file.framePosition<file.length){AVAudioPCMBuffer*buffer=[[AVAudioPCMBuffer alloc]initWithPCMFormat:file.processingFormat frameCapacity:4096];if(![file readIntoBuffer:buffer frameCount:(AVAudioFrameCount)MIN((AVAudioFramePosition)4096,file.length-file.framePosition) error:&error]||!buffer.frameLength)break;if(![self convert:buffer ending:NO error:&error])break;}}
        if(scoped)[url stopAccessingSecurityScopedResource];if(error){[self cleanup];[self done:error.localizedDescription];}else [self finishASR];
    });
}
- (void)replay {if(self.busy)return;[self.playback stop];NSError*error=nil;[AVAudioSession.sharedInstance setCategory:AVAudioSessionCategoryPlayback mode:AVAudioSessionModeDefault options:0 error:&error];[AVAudioSession.sharedInstance setActive:YES error:&error];NSURL*file=[[NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject URLByAppendingPathComponent:@"speech-last.caf"];self.player=[[AVAudioPlayer alloc]initWithContentsOfURL:file error:&error];if(![self.player play])self.status.text=error.localizedDescription ?: @"暂无可播放音频";}
- (void)cancel {self.cancelled=YES;[self.downloadTask cancel];[self.player stop];[self.playback stop];[_nativeLock lock];ortts_tts_cancel(_tts);ortts_asr_cancel(_asr);ortts_asr_stream_cancel(_incremental);[_nativeLock unlock];if(self.recording)[self stopCapture:YES];if(self.busy)[self message:@"正在停止…"];}
- (void)viewWillDisappear:(BOOL)animated{[super viewWillDisappear:animated];[self cancel];dispatch_async(OrTTSDemoQueue(),^{[self cleanup];});}
- (void)interrupted:(NSNotification*)note{[self cancel];dispatch_async(OrTTSDemoQueue(),^{[self cleanup];});}
- (void)didReceiveMemoryWarning{[super didReceiveMemoryWarning];[self cancel];dispatch_async(OrTTSDemoQueue(),^{[self cleanup];});}
- (void)dealloc{[NSNotificationCenter.defaultCenter removeObserver:self];[_session invalidateAndCancel];}
@end
