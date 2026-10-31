#import <AVFoundation/AVFoundation.h>
// All methods run on the main queue; PCM must be copied before enqueue.
@interface StreamPlayback : NSObject
@property (nonatomic, copy) void (^completion)(void);
@property (nonatomic, readonly) BOOL active;
- (BOOL)prepare:(NSError **)error;
- (void)enqueue:(AVAudioPCMBuffer *)buffer;
- (void)finish;
- (void)stop;
@end
