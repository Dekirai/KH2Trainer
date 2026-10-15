#include "source-snapshots/src__KH2Trainer.Bridge__MissionCounterSupport.h"
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

// Independent decimal oracle: replace a character in a ten-digit decimal string.
// This intentionally does not use the production division/power expression.
int main() {
    uint64_t cases=0,failures=0;
    auto check=[&](bool ok) { ++cases; if(!ok) ++failures; };
    std::vector<int32_t> values={0,1,9,10,99,100,999999999,1000000000,1999999999,2000000000,2147483646,INT32_MAX};
    uint32_t seed=0x91b67u;
    for(unsigned i=0;i<2048;++i) { seed=seed*1664525u+1013904223u; values.push_back(static_cast<int32_t>(seed&0x7fffffffu)); }
    const int32_t deltas[]={INT32_MIN,INT32_MIN+1,-2000000000,-1000000000,-1,0,1,1000000000,2000000000,INT32_MAX-1,INT32_MAX};
    for(int32_t value:values) for(int32_t maximum:{value,INT32_MAX}) {
        for(unsigned position=0;position<10;++position) for(unsigned digit=0;digit<10;++digit) {
            std::string decimal=std::to_string(value);
            decimal=std::string(10-decimal.size(),'0')+decimal;
            decimal[9-position]=static_cast<char>('0'+digit);
            const auto expected=std::stoll(decimal);
            const bool accepted=expected<=maximum;
            int32_t result=-13579;
            const bool actual=mission_counter::Digit(value,maximum,position,digit,result);
            check(actual==accepted && result==(accepted?static_cast<int32_t>(expected):-13579));
        }
        for(int32_t delta:deltas) {
            // Compare mathematical signed integers, not DWORD wrap or clamping.
            const auto expected=static_cast<long long>(value)+delta;
            const bool accepted=expected>=0 && expected<=maximum;
            int32_t result=-24680;
            const bool actual=mission_counter::Delta(value,maximum,delta,result);
            check(actual==accepted && result==(accepted?static_cast<int32_t>(expected):-24680));
        }
    }
    for(int32_t current:{INT32_MIN,-1,0,1,INT32_MAX}) for(int32_t maximum:{INT32_MIN,-1,0,1,INT32_MAX}) {
        if(current>=0 && maximum>=current) continue;
        int32_t result=123;
        check(!mission_counter::Delta(current,maximum,0,result) && result==123);
        check(!mission_counter::Digit(current,maximum,0,0,result) && result==123);
    }
    for(unsigned invalid:{10u,31u,32u,100u,0xffffffffu}) {
        int32_t result=456;
        check(!mission_counter::Digit(0,INT32_MAX,invalid,0,result) && result==456);
        check(!mission_counter::Digit(0,INT32_MAX,0,invalid,result) && result==456);
    }
    std::printf("{\"success\":%s,\"cases\":%llu,\"failures\":%llu,\"oracle\":\"Decimal string replacement and mathematical signed delta\",\"liveGame\":false}\n",failures?"false":"true",cases,failures);
    return failures?1:0;
}
