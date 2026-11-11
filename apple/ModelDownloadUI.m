#import "ModelDownloadUI.h"
#import <Network/Network.h>
#import <objc/runtime.h>
static char PendingKey;
void OrTTSConfirmModelDownload(UIViewController*owner,void(^start)(BOOL)){
 if([objc_getAssociatedObject(owner,&PendingKey)boolValue])return;
 objc_setAssociatedObject(owner,&PendingKey,@YES,OBJC_ASSOCIATION_RETAIN_NONATOMIC);
 dispatch_queue_t queue=dispatch_queue_create("com.orient.ortts.download-network",DISPATCH_QUEUE_SERIAL);
 nw_path_monitor_t monitor=nw_path_monitor_create();__block BOOL finished=NO;
 void(^complete)(BOOL)=^(BOOL safe){if(finished)return;finished=YES;nw_path_monitor_cancel(monitor);dispatch_async(dispatch_get_main_queue(),^{
  objc_setAssociatedObject(owner,&PendingKey,@NO,OBJC_ASSOCIATION_RETAIN_NONATOMIC);
  if(safe){start(NO);return;}if(owner.presentedViewController)return;
  UIAlertController*a=[UIAlertController alertControllerWithTitle:@"允许使用移动数据下载？" message:@"当前为移动数据、计费网络、低数据模式，或无法确认网络类型。模型可能需要数百 MB 至数 GB。默认仅使用非计费网络；本次允许后可能消耗较多流量。" preferredStyle:UIAlertControllerStyleAlert];
  [a addAction:[UIAlertAction actionWithTitle:@"取消，等 Wi-Fi" style:UIAlertActionStyleCancel handler:nil]];
  [a addAction:[UIAlertAction actionWithTitle:@"本次允许" style:UIAlertActionStyleDefault handler:^(UIAlertAction*x){start(YES);}]];[owner presentViewController:a animated:YES completion:nil];
 });};
 nw_path_monitor_set_queue(monitor,queue);nw_path_monitor_set_update_handler(monitor,^(nw_path_t path){complete(nw_path_get_status(path)==nw_path_status_satisfied&&!nw_path_uses_interface_type(path,nw_interface_type_cellular)&&!nw_path_is_expensive(path)&&!nw_path_is_constrained(path));});nw_path_monitor_start(monitor);
 dispatch_after(dispatch_time(DISPATCH_TIME_NOW,2*NSEC_PER_SEC),queue,^{complete(NO);});
}
NSURLSessionConfiguration*OrTTSModelDownloadConfiguration(BOOL allowed){
 NSURLSessionConfiguration*c=NSURLSessionConfiguration.ephemeralSessionConfiguration;c.URLCredentialStorage=nil;c.HTTPShouldSetCookies=NO;c.timeoutIntervalForRequest=15;c.timeoutIntervalForResource=1800;c.allowsCellularAccess=allowed;c.allowsExpensiveNetworkAccess=allowed;c.allowsConstrainedNetworkAccess=allowed;c.waitsForConnectivity=NO;return c;
}
dispatch_source_t OrTTSObserveModelDownload(NSURLSessionDownloadTask*task,int64_t total,void(^update)(NSString*,double)){
 dispatch_source_t timer=dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER,0,0,dispatch_get_global_queue(QOS_CLASS_UTILITY,0));dispatch_source_set_timer(timer,DISPATCH_TIME_NOW,250*NSEC_PER_MSEC,50*NSEC_PER_MSEC);
 dispatch_source_set_event_handler(timer,^{int64_t received=task.countOfBytesReceived;double fraction=total>0?MIN(1.,MAX(0.,(double)received/total)):0;NSString*state=total>0&&received>=total?@"下载完成，正在校验":task.state==NSURLSessionTaskStateRunning?@"下载":@"连接中";update([NSString stringWithFormat:@"%@ · %.1f / %.1f MB · %.1f%%",state,received/1e6,total/1e6,fraction*100],fraction);});dispatch_resume(timer);return timer;
}
