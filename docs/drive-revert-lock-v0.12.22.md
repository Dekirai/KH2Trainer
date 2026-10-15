# Twitch Drive Form: Revert lock — v0.12.22

Twitch rewards for Valor, Wisdom, Limit, Master, Final, Antiform and Drive Roulette
block the in-game **Revert / Zurück** command while the reward is active. The
effect first acquires its own lock and confirms it before requesting a form.
Points are kept only once both the requested form and that lock are confirmed.

## Behavior

- Extending the same reward keeps the same lock for its extended duration.
- Replacing a form reward releases the old lock before acquiring the new one.
  Existing native Revert-then-transform behavior is retained.
- Reward expiry, Stop all, game disconnect and Disable all effects release the
  reward's lock. Cleanup does not require a playable character or unpaused scene.
- **Kick Out of Drive Form** retains its existing interrupt behavior: it requests
  the native return first, then ends the running reward. A refused Kick Out does
  not remove the running reward's lock.
- The trainer's explicit Drive controls remain available. If the form or owned
  lock is lost, the reward ends instead of repeatedly forcing it back.
- Stale or missing observations do not count as a successful form or lock.
  Unconfirmed lock cleanup remains pending and is retried.

Restart KH2 before connecting this version, so that the previous native bridge
is replaced. This change adds no reward settings or manual feature entries.

## Native implementation

The original executable's command resolver follows a command to its root row.
Root command 5 is Revert. Its form-disable field is a 16-bit mask at row offset
44; bits 1 through 6 cover the six supported Drive Forms. The availability
validator uses that mask for the menu command. Some timer-driven native return
paths also use this validator, so those returns are held while the lock is active.
The reward releases the lock before requesting its own direct native Revert.

The bridge validates the original code and the current system BAR, allocation,
command table and root row. The table must be within the original executable's
system arena. Each reward has a random owner token and each native bridge has an
independent random session token. Internal command 1488 acquires/releases this
ownership; snapshot slots 488–492 report its state, owner and session.

Cleanup removes only mask bits the trainer originally added, while the full
observed mask and binding still match. An unreadable or temporarily nonwritable
owned table leaves cleanup pending. A changed binding or foreign mask value
ends ownership without overwriting that change. Consequently, cleanup does not
promise to enable Revert if another mod replaces the mask. An identical external
in-place reinitialization between observations is outside this ownership model.

An idle lock does not scan the command table. Active validation and cleanup run
on the game update thread, including cleanup retries after the host heartbeat
expires. The lock does not depend on character lifetime hooks.

## Validation scope

The command-mask mechanism was checked against the original executable in IDA
and against its PE bytes. Isolated native and managed fixtures cover ownership,
restoration, effect lifecycle and failure paths. The release build also runs the
repository's complete native, Core, Twitch and offscreen UI suites and verifies
the embedded bridge in the portable EXE.

These checks do not establish live gameplay behavior. No live KH2 session,
save file or Twitch account is modified for this release's verification.
