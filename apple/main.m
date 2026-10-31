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
@interface Scene : UIResponder <UIWindowSceneDelegate>
@property (nonatomic, strong) UIWindow *window;
@end
@implementation Scene
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    if (![scene isKindOfClass:UIWindowScene.class]) return;
    self.window=[[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    self.window.rootViewController=[Demo new]; [self.window makeKeyAndVisible];
    NSLog(@"OrTTS scene ready");
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
