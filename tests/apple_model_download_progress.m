#import "ModelDownloadUI.h"
int main(int argc,char**argv){@autoreleasepool{
 NSURLSessionConfiguration*c=OrTTSModelDownloadConfiguration(NO);if(c.allowsCellularAccess||c.allowsExpensiveNetworkAccess||c.allowsConstrainedNetworkAccess)return 1;
 NSURLSessionConfiguration*yes=OrTTSModelDownloadConfiguration(YES);if(!yes.allowsCellularAccess||!yes.allowsExpensiveNetworkAccess||!yes.allowsConstrainedNetworkAccess)return 2;
 if(argc!=2)return 3;dispatch_semaphore_t done=dispatch_semaphore_create(0);__block BOOL success=NO;__block BOOL intermediate=NO;__block double previous=0;__block BOOL monotonic=YES;
 NSURLSession*s=[NSURLSession sessionWithConfiguration:c];NSURLSessionDownloadTask*t=[s downloadTaskWithURL:[NSURL URLWithString:@(argv[1])]completionHandler:^(NSURL*url,NSURLResponse*r,NSError*e){success=!e&&((NSHTTPURLResponse*)r).statusCode==200;dispatch_semaphore_signal(done);}];
 dispatch_source_t meter=OrTTSObserveModelDownload(t,1048576,^(NSString*text,double fraction){if(fraction>0&&fraction<1)intermediate=YES;if(fraction<previous||fraction<0||fraction>1)monotonic=NO;previous=fraction;NSLog(@"%@",text);});[t resume];BOOL timeout=dispatch_semaphore_wait(done,dispatch_time(DISPATCH_TIME_NOW,15*NSEC_PER_SEC));dispatch_source_cancel(meter);[s invalidateAndCancel];
 if(timeout||!success||!intermediate||!monotonic)return 4;NSLog(@"PASS: byte progress and Wi-Fi-only/default versus one-job opt-in configuration");return 0;
}}
