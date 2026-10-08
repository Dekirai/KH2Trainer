#pragma once
#include <stdint.h>
#include <stddef.h>

// Protocol-v4 extension inside the existing 1024-byte reserved request/response area.
// Tokens and float bits are binary integers, never transported through doubles.
namespace movement_tx {
constexpr uint32_t Magic=0x31564F4D; // MOV1, little endian
constexpr uint16_t Schema=1;
constexpr unsigned RequestOffset=1024,ResponseOffset=1152;
constexpr unsigned Command=1466,Capability=466,GenerationLow=467,GenerationHigh=468;
constexpr unsigned InstanceLow=469,InstanceHigh=470,ObserverStatus=471;
enum class Operation:uint32_t { Acquire=1,Reapply=2,ReleaseIntent=3,QueryOperation=4,QueryLease=5,AcknowledgeReceipt=6 };
enum class Outcome:uint32_t { Invalid=0,Applied=1,Reapplied=2,ReleaseAccepted=3,LeaseObserved=4,ReceiptAcknowledged=5,OperationUnknown=6,Rejected=7 };
enum class State:uint32_t { None=0,Active=1,ReleasePending=2,Released=3,Superseded=4,Destroyed=5,Uncertain=6 };
enum class Reason:uint32_t {
    None=0,UnsupportedSchema=1,InvalidRequest=2,StaleBridge=3,ActorMismatch=4,NotReady=5,
    ExpectedMismatch=6,InvalidValues=7,JournalFull=8,LeaseNotFound=9,LeaseConflict=10,
    RevisionMismatch=11,RequestIdConflict=12,ObserverUnavailable=13,ObserverFault=14,
    Expired=15,HostExpired=16,NoChange=17,WriteFault=18,ReceiptNotFound=19,NotOwner=20,WrongThread=21
};
enum Flags:uint32_t { IdentityKnown=1,ObservedKnown=2,HasReceipt=4 };
struct Request {
    uint32_t magic; uint16_t schema,size;
    uint64_t clientId,opId,bridgeInstance,actorGeneration,leaseId;
    Operation operation; uint32_t mask;
    uint32_t expectedBits[4],desiredBits[4];
    uint64_t expectedLeaseRevision,effectOwnerId;
    uint32_t flags,reserved0;
    uint64_t targetOpId,reserved1;
};
struct Response {
    uint32_t magic; uint16_t schema,size;
    uint64_t clientId,opId,bridgeInstance,actorGeneration,leaseId,revision,effectOwnerId;
    Outcome outcome; uint32_t mask,appliedMask,restoredMask,supersededMask;
    State journalState;
    uint32_t originalBits[4],appliedBits[4],observedBits[4];
    uint32_t requestSequence; Reason reason; uint32_t tick,flags;
    uint64_t receiptOpId,reserved[4];
};
static_assert(sizeof(Request)==128 && offsetof(Request,expectedBits)==56 && offsetof(Request,targetOpId)==112,"Movement request layout");
static_assert(sizeof(Response)==192 && offsetof(Response,originalBits)==88 && offsetof(Response,requestSequence)==136 && offsetof(Response,receiptOpId)==152,"Movement response layout");
}
