#import <Foundation/Foundation.h>
BOOL OrTTSValidSharedAsset(NSURL *file, NSDictionary *entry);
NSDictionary *OrTTSSharedAssetIndex(NSArray<NSURL*> *roots);
BOOL OrTTSReuseSharedAsset(NSDictionary *index, NSDictionary *entry, NSURL *target, NSError **error);
