namespace KH2Trainer.Core;

/// <summary>A nonzero status received in the acknowledgement of an ordinary bridge command.
/// Its code alone does not generally prove that a handler made no writes.</summary>
public sealed class BridgeCommandRejectedException(int code, string message) : InvalidOperationException(message)
{
    public int Code { get; } = code;
}
