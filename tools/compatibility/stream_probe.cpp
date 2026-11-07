#include "audiocpp.h"
#include <cmath>
#include <iostream>
#include <stdexcept>
struct Capture {size_t chunks=0,samples=0;bool stop=false,bad=false;};
static void check(audiocpp_status s){if(s!=AUDIOCPP_OK)throw std::runtime_error(audiocpp_last_error());}
static int receive(const audiocpp_event*e,void*u){auto&c=*(Capture*)u;const float*p=nullptr;size_t n=0;int r=0,ch=0;
 if(audiocpp_result_audio(audiocpp_event_as_result(e),&p,&n,&r,&ch)!=AUDIOCPP_OK||!n)return 0;
 c.chunks++;c.samples+=n;if(!p||r!=24000||ch!=1)c.bad=true;else for(size_t i=0;i<n;i++)if(!std::isfinite(p[i]))c.bad=true;
 return c.bad||c.stop;
}
int main(int argc,char**argv){if(argc!=2)return 2;audiocpp_registry*r=nullptr;audiocpp_model*m=nullptr;audiocpp_session*s=nullptr;audiocpp_request*q=nullptr;audiocpp_result*a=nullptr;int exitCode=0;
 try{check(audiocpp_registry_create(nullptr,&r));audiocpp_model_config config{"kokoro_tts",nullptr,nullptr,nullptr};check(audiocpp_model_load(r,argv[1],&config,nullptr,&m));audiocpp_backend_config b{"cpu",0,4};check(audiocpp_session_create(m,"tts","streaming",&b,nullptr,&s));
 q=audiocpp_request_create();check(audiocpp_request_set_text(q,"今天是十一月七日。请检查身份证和车票。欢迎使用本地语音合成。", "zh"));check(audiocpp_request_set_voice_id(q,"zf_xiaobei"));check(audiocpp_request_set_option(q,"text_chunk_size","12"));
 Capture c;c.stop=true;check(audiocpp_stream_set_callback(s,receive,&c));auto status=audiocpp_stream_start(s,q);std::cout<<"cancel_status="<<status<<" cancel_chunks="<<c.chunks<<"\n";if(c.chunks!=1||c.bad)throw std::runtime_error("cancel callback invariant");check(audiocpp_stream_reset(s));
 c={};check(audiocpp_stream_set_callback(s,receive,&c));check(audiocpp_stream_start(s,q));check(audiocpp_stream_set_callback(s,nullptr,nullptr));check(audiocpp_stream_finish(s,&a));const float*p=nullptr;size_t n=0;int rate=0,ch=0;check(audiocpp_result_audio(a,&p,&n,&rate,&ch));if(c.bad||c.chunks<2||c.samples!=n)throw std::runtime_error("PCM aggregation/reset invariant");
 std::cout<<"reset_success=1 chunks="<<c.chunks<<" callback_samples="<<c.samples<<" final_samples="<<n<<" sample_rate="<<rate<<"\n";
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";exitCode=1;}
 audiocpp_result_free(a);audiocpp_request_free(q);audiocpp_session_free(s);audiocpp_model_free(m);audiocpp_registry_free(r);return exitCode;}
