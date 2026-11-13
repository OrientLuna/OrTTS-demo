// Isolated UIKit test harness, not a change to Demo/OrTavern UI or downloads.
#import <UIKit/UIKit.h>
#include <stdio.h>
#include <stdlib.h>
extern int ortts_rust_cancel_probe(const char *, const char *, const char *);
@interface ProbeDelegate : UIResponder <UIApplicationDelegate>
@end
@interface ProbeSceneDelegate : UIResponder <UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@end
@implementation ProbeSceneDelegate
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    self.window.rootViewController = [UIViewController new];
    [self.window makeKeyAndVisible];
}
@end
@implementation ProbeDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        @autoreleasepool {
            NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
            NSString *root = [documents stringByAppendingPathComponent:@"models"];
            NSString *output = [documents stringByAppendingPathComponent:@"rust-cancellation.json"];
            int status = ortts_rust_cancel_probe(root.UTF8String,
                "78954b071cabd84e126a9a5e27ad5903cd10e574ae0509da5d7254e5023e2fd4", output.UTF8String);
            NSData *data = [NSData dataWithContentsOfFile:output];
            NSDictionary *json = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
            NSMutableDictionary *receipt = json ? [json mutableCopy] : [@{@"status": @"failed"} mutableCopy];
            NSProcessInfo *host = NSProcessInfo.processInfo;
            receipt[@"os"] = host.operatingSystemVersionString;
            receipt[@"device_model"] = UIDevice.currentDevice.model;
            receipt[@"thermal_state_end"] = @(host.thermalState);
            receipt[@"low_power_mode"] = @(host.lowPowerModeEnabled);
            receipt[@"exit_status"] = @(status);
            NSData *final = [NSJSONSerialization dataWithJSONObject:receipt options:NSJSONWritingPrettyPrinted error:nil];
            [final writeToFile:output atomically:YES];
            fprintf(stdout, "RUST_CANCEL_PROBE_STATUS=%d REPORT=%s\n", status, output.UTF8String);
            fflush(stdout);
            // Isolated command-like acceptance app: exit only AFTER Rust returns,
            // all task/engine owners are dropped and the receipt is persisted.
            exit(status);
        }
    });
    return YES;
}
@end
int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(ProbeDelegate.class)); }
}
