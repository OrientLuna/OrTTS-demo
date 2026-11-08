#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
NSArray<NSURL *> *OrTTSDownloadCandidates(NSString *primary,NSArray *alternatives,NSError **error);
NSString *OrTTSDownloadChannelName(NSURL *url);
void OrTTSDownloadSucceeded(NSURL *url);
UIButton *OrTTSDownloadChannelButton(UIViewController *owner);

void OrTTSRefreshDownloadChannelButton(UIButton *button);
