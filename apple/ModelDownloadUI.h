#import <UIKit/UIKit.h>
void OrTTSConfirmModelDownload(UIViewController *owner, void (^start)(BOOL allowMetered));
NSURLSessionConfiguration *OrTTSModelDownloadConfiguration(BOOL allowMetered);
dispatch_source_t OrTTSObserveModelDownload(NSURLSessionDownloadTask *task, int64_t total, void (^update)(NSString *text, double fraction));
