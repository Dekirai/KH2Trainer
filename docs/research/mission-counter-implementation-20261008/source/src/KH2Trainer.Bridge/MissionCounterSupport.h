#pragma once
#include <stdint.h>

// Pure arithmetic for the trainer commands, not the unchecked native BDX
// delta/digit adapters. No clamping or DWORD wrap is part of this contract.
namespace mission_counter {
constexpr unsigned DeltaSlot=477,DigitSlot=478;
inline bool Valid(int32_t current,int32_t maximum) {
    return current>=0 && maximum>=current;
}
inline bool Target(int64_t value,int32_t maximum,int32_t& output) {
    if(value<0 || value>maximum || value>INT32_MAX) return false;
    output=static_cast<int32_t>(value); return true;
}
inline bool Delta(int32_t current,int32_t maximum,int32_t delta,int32_t& output) {
    return Valid(current,maximum) && Target(static_cast<int64_t>(current)+delta,maximum,output);
}
inline bool Digit(int32_t current,int32_t maximum,unsigned position,unsigned digit,int32_t& output) {
    if(!Valid(current,maximum) || position>9 || digit>9) return false;
    int64_t power=1;
    for(unsigned i=0;i<position;++i) power*=10;
    const int64_t oldDigit=(static_cast<int64_t>(current)/power)%10;
    return Target(static_cast<int64_t>(current)+(static_cast<int64_t>(digit)-oldDigit)*power,maximum,output);
}
}
