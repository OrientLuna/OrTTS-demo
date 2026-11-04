#include "binding_checks.h"
#include <iostream>
#include <cstdlib>
#include <fstream>
int main(int argc,char**argv){try{
 if(argc!=3)throw std::runtime_error("bundle and trusted SHA required");
 std::string root=argv[1],sha=argv[2];auto m=engine::io::json::parse_file(std::filesystem::path(root)/"MANIFEST.json");setenv("ORTTS_LC_VARIANT","base",1);
 tail_binding::validate(m,root,"","","",sha);
 bool rejected=false;try{tail_binding::validate(m,root,"","","",std::string(64,'0'));}catch(...){rejected=true;}if(!rejected)throw std::runtime_error("wrong SHA accepted");
 unsetenv("ORTTS_LC_VARIANT");rejected=false;try{tail_binding::validate(m,root,"","","",sha);}catch(...){rejected=true;}if(!rejected)throw std::runtime_error("dequant accepted as LFM");
 std::cout<<"PASS actual canonical18; wrong manifest SHA and wrong decoder rejected; no LFM files supplied\n";
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
