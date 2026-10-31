#import "StreamPlayback.h"
@interface StreamPlayback ()
@property AVAudioEngine *engine;
@property AVAudioPlayerNode *node;
@property NSUInteger pending, samples, epoch;
@property BOOL ended, started, active;
@end
@implementation StreamPlayback
- (BOOL)prepare:(NSError **)error {
    self.engine=[AVAudioEngine new]; self.node=[AVAudioPlayerNode new];
    AVAudioSession *session=AVAudioSession.sharedInstance;
    if (![session setCategory:AVAudioSessionCategoryPlayback error:error] || ![session setActive:YES error:error]) return NO;
    [self.engine attachNode:self.node];
    AVAudioFormat *format=[[AVAudioFormat alloc] initWithCommonFormat:AVAudioPCMFormatFloat32 sampleRate:24000 channels:1 interleaved:NO];
    [self.engine connect:self.node to:self.engine.mainMixerNode format:format];
    self.active=[self.engine startAndReturnError:error]; return self.active;
}
- (void)drained {
    if (self.ended && self.pending==0 && self.active) {
        [self stop]; if (self.completion) self.completion();
    }
}
- (void)enqueue:(AVAudioPCMBuffer *)buffer {
    if (!self.active) return;
    self.pending++; self.samples+=buffer.frameLength; NSUInteger epoch=self.epoch;
    __weak StreamPlayback *weakSelf=self;
    [self.node scheduleBuffer:buffer completionCallbackType:AVAudioPlayerNodeCompletionDataPlayedBack completionHandler:^(AVAudioPlayerNodeCompletionCallbackType type) {
        dispatch_async(dispatch_get_main_queue(), ^{
            StreamPlayback *s=weakSelf; if (!s || s.epoch!=epoch || !s.active) return;
            if (s.pending) s.pending--; [s drained];
        });
    }];
    // Small initial buffer absorbs generation jitter without waiting for full audio.
    if (!self.started && self.samples>=11520) { self.started=YES; [self.node play]; NSLog(@"OrTTS stream playback started"); }
}
- (void)finish {
    self.ended=YES;
    if (!self.started && self.pending) { self.started=YES; [self.node play]; }
    [self drained];
}
- (void)stop { self.epoch++; self.active=NO; [self.node stop]; [self.engine stop]; self.pending=0; }
@end
