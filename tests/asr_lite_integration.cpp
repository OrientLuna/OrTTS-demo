#include "ortts_speech.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <sstream>
#include <thread>
#include <vector>
#include <sys/resource.h>
using Clock=std::chrono::steady_clock;
static void check(bool ok,const char*why){if(!ok)throw std::runtime_error(std::string(why)+": "+ortts_last_error());}
struct Events {size_t partial=0,final=0;bool cancel=false;std::string text;};
static int receive(void*u,const ortts_asr_stream_event*e){auto&v=*static_cast<Events*>(u);check(e&&e->struct_size==sizeof(*e),"event layout");if(e->endpoint==ORTTS_ASR_PARTIAL)++v.partial;else{++v.final;if(!v.text.empty())v.text+=" ";v.text+=e->text;}return v.cancel;}
static std::string run(ortts_asr_stream*e,const std::vector<float>&p,Events&events){for(size_t off=0;off<p.size();off+=3200)check(ortts_asr_stream_accept(e,p.data()+off,std::min(size_t(3200),p.size()-off),receive,&events)==ORTTS_OK,"accept");check(events.partial>0,"partial before finish");check(ortts_asr_stream_finish(e,receive,&events)==ORTTS_OK,"finish");auto finals=events.final;check(ortts_asr_stream_finish(e,receive,&events)==ORTTS_OK&&events.final==finals,"idempotent finish");return events.text;}
#ifdef ORTTS_ASR_APP_ENTRY
extern "C" int ortts_asr_lite_native_test(int argc,char**argv)
#else
int main(int argc,char**argv)
#endif
{try{
 check(argc==3||argc==4||argc==5,"arguments: model-root raw-f32");std::ifstream f(argv[2],std::ios::binary|std::ios::ate);check(bool(f),"input");auto bytes=f.tellg();check(bytes>0&&bytes%4==0,"f32 input");f.seekg(0);std::vector<float>audio(size_t(bytes)/4);f.read(reinterpret_cast<char*>(audio.data()),bytes);
 ortts_speech_config c{};c.struct_size=sizeof(c);c.family="zipformer_bilingual";c.model_path=argv[1];c.threads=2;c.streaming=1;ortts_asr_stream_config v{sizeof(v),400,1000,15000,0,.003F};ortts_asr_stream*e=nullptr;auto load=Clock::now();check(ortts_asr_stream_create(&c,&v,&e)==ORTTS_OK,"create");double cold=std::chrono::duration<double,std::milli>(Clock::now()-load).count();
 Events first;auto start=Clock::now();std::string expected=run(e,audio,first);double api=std::chrono::duration<double,std::milli>(Clock::now()-start).count();check(!expected.empty(),"nonempty final");check(ortts_asr_stream_reset(e)==ORTTS_OK,"reset");
 Events bad;float nan=std::numeric_limits<float>::quiet_NaN();check(ortts_asr_stream_accept(e,&nan,1,receive,&bad)==ORTTS_INVALID,"nonfinite transaction");
 ortts_asr_stream_cancel(e);check(ortts_asr_stream_accept(e,audio.data(),1,receive,&bad)==ORTTS_CANCELLED,"sticky idle cancel");check(ortts_asr_stream_reset(e)==ORTTS_OK,"reset cancel");
 Events stop;stop.cancel=true;ortts_status status=ORTTS_OK;for(size_t off=0;off<audio.size()&&status==ORTTS_OK;off+=3200)status=ortts_asr_stream_accept(e,audio.data()+off,std::min(size_t(3200),audio.size()-off),receive,&stop);check(status==ORTTS_CANCELLED,"callback cancellation");check(ortts_asr_stream_reset(e)==ORTTS_OK,"recover callback");Events recovered;auto warm_start=Clock::now();check(run(e,audio,recovered)==expected,"callback recovery equality");double warm_api=std::chrono::duration<double,std::milli>(Clock::now()-warm_start).count();check(ortts_asr_stream_reset(e)==ORTTS_OK,"reset cross-thread");
 std::atomic<bool>sent{false};std::atomic<int64_t>requested_ns{0};std::thread killer([&]{std::this_thread::sleep_for(std::chrono::milliseconds(5));requested_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count();ortts_asr_stream_cancel(e);sent=true;});status=ORTTS_OK;auto cancel_start=Clock::now();Events cross;for(size_t off=0;off<audio.size()&&status==ORTTS_OK;off+=3200)status=ortts_asr_stream_accept(e,audio.data()+off,std::min(size_t(3200),audio.size()-off),receive,&cross);killer.join();if(status==ORTTS_OK)status=ortts_asr_stream_finish(e,receive,&cross);double cancellation=std::chrono::duration<double,std::milli>(Clock::now()-cancel_start).count();double request_to_return=(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count()-requested_ns.load())/1e6;check(sent&&status==ORTTS_CANCELLED,"cross thread cancellation");check(ortts_asr_stream_reset(e)==ORTTS_OK,"recover cross-thread");Events after;check(run(e,audio,after)==expected,"cross thread recovery equality");check(ortts_asr_stream_reset(e)==ORTTS_OK,"reset silence");std::vector<float>silence(16000*3);Events quiet;for(size_t off=0;off<silence.size();off+=3200)check(ortts_asr_stream_accept(e,silence.data()+off,std::min(size_t(3200),silence.size()-off),receive,&quiet)==ORTTS_OK,"silence accept");check(ortts_asr_stream_finish(e,receive,&quiet)==ORTTS_OK&&quiet.text.empty(),"exact silence no hallucination");ortts_asr_stream_free(e);
 if(argc>=4){std::ofstream out(argv[3]);out<<expected;}
 struct rusage usage{};getrusage(RUSAGE_SELF,&usage);
 std::ostringstream json;json<<"{\"ok\":true,\"cold_load_ms\":"<<cold<<",\"first_api_ms\":"<<api<<",\"audio_s\":"<<audio.size()/16000.<<",\"first_rtf\":"<<api/1000/(audio.size()/16000.)<<",\"warm_api_ms\":"<<warm_api<<",\"warm_rtf\":"<<warm_api/1000/(audio.size()/16000.)<<",\"partials\":"<<first.partial<<",\"finals\":"<<first.final<<",\"cross_thread_cancel_operation_ms\":"<<cancellation<<",\"cancel_request_to_return_ms_upper_bound\":"<<request_to_return<<",\"peak_rss_native_units\":"<<usage.ru_maxrss<<"}\n";std::cout<<json.str();if(argc==5){std::ofstream report(argv[4]);report<<json.str();}return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
