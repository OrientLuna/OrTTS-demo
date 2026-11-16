#import <Foundation/Foundation.h>
#import <AVFoundation/AVFoundation.h>
#import <TargetConditionals.h>
#import "ortts_engine.h"
#if TARGET_OS_IOS
#import <UIKit/UIKit.h>
#endif

static NSString *Synthesize(NSString *root, NSString *variant, NSString *sha, NSString *text) {
    ortts_config c = {0}; c.struct_size = sizeof(c);
    c.asset_root = root.UTF8String; c.variant = variant.UTF8String;
    c.bridge_manifest_sha256 = sha.UTF8String; c.threads = 4; c.streaming = 0;
    ortts_engine *engine = NULL; ortts_audio *audio = NULL;
    if (ortts_engine_create(&c, &engine) != ORTTS_OK)
        return [NSString stringWithUTF8String:ortts_last_error()];
    ortts_request r = {0}; r.struct_size = sizeof(r); r.text = text.UTF8String; r.seed = 42; r.max_tokens = 513;
    NSString *error = nil;
    if (ortts_engine_synthesize(engine, &r, NULL, NULL, &audio) != ORTTS_OK) {
        error = [NSString stringWithUTF8String:ortts_last_error()];
    } else {
        AVAudioFormat *format = [[AVAudioFormat alloc] initWithCommonFormat:AVAudioPCMFormatFloat32 sampleRate:ortts_audio_sample_rate(audio) channels:1 interleaved:NO];
        size_t count = ortts_audio_sample_count(audio);
        AVAudioPCMBuffer *buffer = [[AVAudioPCMBuffer alloc] initWithPCMFormat:format frameCapacity:(AVAudioFrameCount)count];
        buffer.frameLength = (AVAudioFrameCount)count;
        memcpy(buffer.floatChannelData[0], ortts_audio_samples(audio), count * sizeof(float));
        NSURL *url = [[NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject URLByAppendingPathComponent:@"ortts-output.caf"];
        [NSFileManager.defaultManager createDirectoryAtURL:[url URLByDeletingLastPathComponent] withIntermediateDirectories:YES attributes:nil error:nil];
        NSError *e = nil;
        AVAudioFile *file = [[AVAudioFile alloc] initForWriting:url settings:format.settings error:&e];
        if (!file || ![file writeFromBuffer:buffer error:&e]) error = e.localizedDescription;
        else NSLog(@"Audio saved: %@", url.path);
    }
    if (audio) ortts_audio_free(audio);
    ortts_engine_free(engine);
    return error;
}
#if TARGET_OS_IOS
#import "Demo.h"
#import "SpeechDemo.h"
#if ORTTS_INTERACTION_QA
#import "WorkQueue.h"
extern int ortts_app_concurrency_check(const char*, const char*, const char*, const char*);
#endif
@interface Scene : UIResponder <UIWindowSceneDelegate>
@property (nonatomic, strong) UIWindow *window;
@end
@implementation Scene
#if ORTTS_INTERACTION_QA
- (void)sceneDidEnterBackground:(UIScene*)scene {
    NSArray*args=NSProcessInfo.processInfo.arguments;if(![args containsObject:@"--speech-lifecycle-qa"])return;
    NSUInteger index=[args indexOfObject:@"--speech-run-id"];
    NSDictionary*r=@{@"run_id":index!=NSNotFound&&index+1<args.count?args[index+1]:@"qa",@"application_state":@(UIApplication.sharedApplication.applicationState),@"pid":@(NSProcessInfo.processInfo.processIdentifier)};
    NSURL*documents=[NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    [[NSJSONSerialization dataWithJSONObject:r options:0 error:nil]writeToURL:[documents URLByAppendingPathComponent:@"interaction-background.json"] atomically:YES];
}
#endif
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    if (![scene isKindOfClass:UIWindowScene.class]) return;
    self.window=[[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    Demo *legacy=[Demo new];legacy.tabBarItem=[[UITabBarItem alloc]initWithTitle:@"OrTTS 合成" image:[UIImage systemImageNamed:@"waveform"] tag:0];
    SpeechDemo *speech=[SpeechDemo new];speech.tabBarItem=[[UITabBarItem alloc]initWithTitle:@"其他语音合成" image:[UIImage systemImageNamed:@"speaker.wave.2"] tag:1];
    UITabBarController *tabs=[UITabBarController new];SpeechDemo *asr=[SpeechDemo new];asr.initialTask=1;asr.tabBarItem=[[UITabBarItem alloc]initWithTitle:@"语音识别" image:[UIImage systemImageNamed:@"mic"] tag:2];tabs.viewControllers=@[legacy,speech,asr];
    NSArray*arguments=NSProcessInfo.processInfo.arguments;NSUInteger smoke=[arguments indexOfObject:@"--speech-smoke"];NSString*mode=smoke!=NSNotFound&&smoke+1<arguments.count?arguments[smoke+1]:nil;
    tabs.selectedIndex=mode?([@[@"asr",@"last"] containsObject:mode]?2:1):0;
    self.window.rootViewController=tabs; [self.window makeKeyAndVisible];
    NSLog(@"OrTTS scene ready");
#if ORTTS_INTERACTION_QA
    if([arguments containsObject:@"--tts-asr-concurrency"]){
        UIApplication.sharedApplication.idleTimerDisabled=YES;
        NSURL*documents=[NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
        dispatch_async(OrTTSDemoQueue(),^{OrTTSPerformWithStack(^{
            int status=ortts_app_concurrency_check([documents URLByAppendingPathComponent:@"models-ptq-q4"].path.UTF8String,
                [documents URLByAppendingPathComponent:@"speech-models/paraformer-streaming-zh-en-int8"].path.UTF8String,
                [documents URLByAppendingPathComponent:@"concurrency-input.f32"].path.UTF8String,
                [documents URLByAppendingPathComponent:@"concurrency-result.json"].path.UTF8String);
            NSLog(@"OrTTS concurrency QA completed: %d",status);
            dispatch_async(dispatch_get_main_queue(),^{UIApplication.sharedApplication.idleTimerDisabled=NO;});
        });});
    }
#endif
}
@end
@interface App : UIResponder <UIApplicationDelegate>
@end
@implementation App
- (BOOL)application:(UIApplication *)app didFinishLaunchingWithOptions:(NSDictionary *)options { return YES; }
@end
int main(int argc, char **argv) { @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(App.class)); } }
#else
int main(int argc, char **argv) {
    @autoreleasepool {
        if (argc != 5) { fprintf(stderr, "Usage: ortts-apple MODEL_ROOT P3|P5 TRUSTED_SHA TEXT\n"); return 2; }
        NSString *error = Synthesize(@(argv[1]), @(argv[2]), @(argv[3]), @(argv[4]));
        if (error) { fprintf(stderr, "%s\n", error.UTF8String); return 1; }
        return 0;
    }
}
#endif
