#import "DownloadChannels.h"
static NSString *const ModeKey=@"ortts.download.channel";
static NSString *const SuccessKey=@"ortts.download.lastSuccess";
static NSString *Channel(NSURL *url){NSString*h=url.host.lowercaseString;if([h isEqual:@"huggingface.co"])return @"hf";if([h isEqual:@"hf-mirror.com"])return @"hfmirror";if([h isEqual:@"modelscope.cn"]||[h isEqual:@"www.modelscope.cn"])return @"modelscope";return @"custom";}
static NSString *Name(NSString *channel){return @{@"auto":@"自动",@"hf":@"Hugging Face",@"hfmirror":@"HF Mirror",@"modelscope":@"ModelScope"}[channel]?:@"原地址";}
NSString *OrTTSDownloadChannelName(NSURL *url){return Name(Channel(url));}
void OrTTSDownloadSucceeded(NSURL *url){[NSUserDefaults.standardUserDefaults setObject:Channel(url) forKey:SuccessKey];}
NSArray<NSURL *> *OrTTSDownloadCandidates(NSString *primary,NSArray *alternatives,NSError **error){
 NSMutableOrderedSet<NSString*>*addresses=[NSMutableOrderedSet new];if(primary)[addresses addObject:primary];for(id value in alternatives)if([value isKindOfClass:NSString.class])[addresses addObject:value];
 NSURL*original=[NSURL URLWithString:primary?:@""];NSString*channel=Channel(original);
 if([channel isEqual:@"hf"]||[channel isEqual:@"hfmirror"]){NSURLComponents*c=[NSURLComponents componentsWithURL:original resolvingAgainstBaseURL:NO];c.host=[channel isEqual:@"hf"]?@"hf-mirror.com":@"huggingface.co";if(c.URL)[addresses addObject:c.URL.absoluteString];}
 NSMutableArray<NSURL*>*valid=[NSMutableArray new];for(NSString *address in addresses){NSURL*u=[NSURL URLWithString:address];if(![u.scheme isEqual:@"https"]||!u.host.length||u.user||u.password){if(error)*error=[NSError errorWithDomain:@"OrTTSDownload" code:1 userInfo:@{NSLocalizedDescriptionKey:@"模型下载地址需要有效HTTPS"}];return @[];}[valid addObject:u];}
 NSString*mode=[NSUserDefaults.standardUserDefaults stringForKey:ModeKey]?:@"auto";NSArray*order=[mode isEqual:@"auto"]?@[[NSUserDefaults.standardUserDefaults stringForKey:SuccessKey]?:@"",@"modelscope",@"hfmirror",@"hf",@"custom"]:@[mode];NSMutableArray*result=[NSMutableArray new];
 for(NSString*choice in order)for(NSURL*u in valid)if([Channel(u)isEqual:choice]&&![result containsObject:u])[result addObject:u];
 if(!result.count&&error)*error=[NSError errorWithDomain:@"OrTTSDownload" code:2 userInfo:@{NSLocalizedDescriptionKey:@"该模型没有所选下载通道，请选择自动或其他通道"}];return result;
}
void OrTTSRefreshDownloadChannelButton(UIButton *button){NSString*mode=[NSUserDefaults.standardUserDefaults stringForKey:ModeKey]?:@"auto";[button setTitle:[@"下载通道：" stringByAppendingString:Name(mode)] forState:UIControlStateNormal];}
UIButton *OrTTSDownloadChannelButton(UIViewController *owner){
 UIButton*b=[UIButton buttonWithType:UIButtonTypeSystem];NSString*mode=[NSUserDefaults.standardUserDefaults stringForKey:ModeKey]?:@"auto";[b setTitle:[@"下载通道：" stringByAppendingString:Name(mode)] forState:UIControlStateNormal];
 __weak UIViewController*weakOwner=owner;__weak UIButton*weakButton=b;
 [b addAction:[UIAction actionWithHandler:^(__kindof UIAction*action){UIViewController*vc=weakOwner;if(!vc)return;UIAlertController*sheet=[UIAlertController alertControllerWithTitle:@"下载通道" message:nil preferredStyle:UIAlertControllerStyleAlert];for(NSString*c in @[@"auto",@"hf",@"hfmirror",@"modelscope"]){[sheet addAction:[UIAlertAction actionWithTitle:Name(c) style:UIAlertActionStyleDefault handler:^(UIAlertAction*a){[NSUserDefaults.standardUserDefaults setObject:c forKey:ModeKey];[weakButton setTitle:[@"下载通道：" stringByAppendingString:Name(c)] forState:UIControlStateNormal];}]];}[sheet addAction:[UIAlertAction actionWithTitle:@"取消" style:UIAlertActionStyleCancel handler:nil]];[vc presentViewController:sheet animated:YES completion:nil];}] forControlEvents:UIControlEventTouchUpInside];return b;
}
