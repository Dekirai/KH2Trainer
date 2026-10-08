using System.Globalization;
using KH2Trainer.Core;

namespace KH2Trainer.Twitch;

/// <summary>
/// Every effect viewers can redeem. Effects only use validated trainer features, so the
/// bridge's scene, actor and resource checks still protect the game. Effects in one group
/// change the same part of the game; the engine never runs two of them at once.
/// </summary>
public static class EffectCatalog
{
    public static IReadOnlyList<EffectDefinition> All { get; } = Build();

    public static EffectDefinition? Find(string key) => All.FirstOrDefault(e => e.Key == key);

    // Item IDs from the item catalog (Data/items.json).
    private const int Potion = 1, HiPotion = 2, Ether = 3, Elixir = 4, MegaPotion = 5, MegaEther = 6, Megalixir = 7,
        Tent = 131, DriveRecovery = 274, HighDriveRecovery = 275, ApBoost = 279;

    private static readonly (int Id, string Name, int Weight)[] MysteryItems =
    [
        (Potion, "Potion", 30), (HiPotion, "Hi-Potion", 20), (Ether, "Ether", 20), (Tent, "Tent", 8),
        (MegaPotion, "Mega-Potion", 6), (Elixir, "Elixir", 6), (DriveRecovery, "Drive Recovery", 4),
        (MegaEther, "Mega-Ether", 3), (Megalixir, "Megalixir", 1), (HighDriveRecovery, "High Drive Recovery", 1), (ApBoost, "AP Boost", 1),
    ];

    private static readonly string[] FormNames = ["Base", "Valor Form", "Wisdom Form", "Limit Form", "Master Form", "Final Form", "Antiform"];

    private static IReadOnlyList<EffectDefinition> Build() =>
    [
        // ---- Helpful ------------------------------------------------------------------------
        new()
        {
            Key = "heal", Category = RewardCategory.Help, Cost = 500,
            AllowedRoles = EffectPlayerRoles.FieldPlayers,
            Title = "Heal Player", TitleDe = "Spieler heilen",
            Prompt = "Restores the controlled character's HP. Refunded if health is already full.",
            PromptDe = "Füllt die HP der gesteuerten Figur auf. Bei vollen HP gibt es die Punkte zurück.",
            Features = ["player.heal", "player.hp", "player.hp.max"],
            Check = ctx => Full(ctx, "player.hp", "player.hp.max") ? Readiness.Reject("The current character already has full HP.") : Readiness.Ready,
            Start = ctx => ctx.RunAsync("player.heal"),
        },
        new()
        {
            Key = "restore-mp", Category = RewardCategory.Help, Cost = 300,
            AllowedRoles = EffectPlayerRoles.FieldPlayers,
            Title = "Refill MP", TitleDe = "MP auffüllen",
            Prompt = "Refills the controlled character's MP and ends MP recharge. Supports Sora, Roxas and Mickey.",
            PromptDe = "Füllt die MP der gesteuerten Figur und beendet die MP-Aufladung. Für Sora, Roxas und Micky.",
            Features = ["player.mp.restore", "player.mp", "player.mp.max"],
            Check = ctx =>
            {
                var gauge = MpGauge(ctx, rejectNoGauge: true);
                return gauge.Kind != ReadinessKind.Ready ? gauge :
                    Full(ctx, "player.mp", "player.mp.max") ? Readiness.Reject("The current character already has full MP.") : Readiness.Ready;
            },
            Start = ctx => ctx.RunAsync("player.mp.restore"),
        },
        new()
        {
            Key = "full-restore", Category = RewardCategory.Help, Cost = 800,
            AllowedRoles = EffectPlayerRoles.FieldPlayers,
            Title = "Full Restore (HP + MP)", TitleDe = "Komplett heilen (HP + MP)",
            Prompt = "Restores the controlled character's HP and MP. Refunded if every available gauge is full.",
            PromptDe = "Füllt HP und MP der gesteuerten Figur auf. Sind alle vorhandenen Leisten voll, gibt es die Punkte zurück.",
            Features = ["player.restore", "player.hp", "player.hp.max", "player.mp", "player.mp.max"],
            Check = ctx => Full(ctx, "player.hp", "player.hp.max") && (ctx.Read("player.mp.max") is <= 0 || Full(ctx, "player.mp", "player.mp.max"))
                ? Readiness.Reject("The current character's available HP and MP gauges are already full.") : Readiness.Ready,
            Start = ctx => ctx.RunAsync("player.restore"),
        },
        new()
        {
            Key = "refill-drive", Category = RewardCategory.Help, Cost = 1000,
            Title = "Refill Drive Gauge", TitleDe = "Drive-Leiste auffüllen",
            Prompt = "Fills every Drive bar. Waits until a running Drive Form has ended.",
            PromptDe = "Füllt alle Drive-Balken. Wartet, bis eine laufende Drive-Form vorbei ist.",
            Features = ["player.drive.bars", "player.drive.max", "player.form.id", "player.gauge.mode"],
            Check = ctx =>
            {
                if (InForm(ctx) || GaugeBusy(ctx)) return Readiness.Wait("Waiting for the Drive Form or summon to end.");
                if (ctx.Read("player.drive.max") is not double max) return Readiness.Wait("Waiting for the Drive gauge.");
                return ctx.Read("player.drive.bars") >= max ? Readiness.Reject("The Drive gauge is already full.") : Readiness.Ready;
            },
            Start = ctx => ctx.RunAsync("player.drive.bars", ctx.Read("player.drive.max") ?? 0),
        },
        new()
        {
            Key = "care-package", Category = RewardCategory.Help, Cost = 1000, Amount = 2, AmountLabel = "of each", AmountLabelDe = "je Sorte", MaxAmount = 99,
            Title = "Potion Care Package", TitleDe = "Trank-Care-Paket",
            Prompt = "Adds Potions, Hi-Potions and Ethers to Sora's bag.",
            PromptDe = "Legt Tränke, Hi-Tränke und Äther in Soras Tasche.",
            Features = ["inspect-item", "selected-item-stock", "set-item-stock"], ChangesSaveData = true,
            Start = ctx => GiveItems(ctx, [(Potion, "Potion"), (HiPotion, "Hi-Potion"), (Ether, "Ether")], ctx.Amount),
        },
        new()
        {
            Key = "megalixir", Category = RewardCategory.Help, Cost = 2500, Amount = 1, AmountLabel = "Megalixir(s)", AmountLabelDe = "Megalixier", MaxAmount = 99,
            Title = "Gift a Megalixir", TitleDe = "Megalixier schenken",
            Prompt = "Adds a Megalixir to Sora's bag. Fully restores the whole party when used.",
            PromptDe = "Legt ein Megalixier in Soras Tasche. Heilt beim Benutzen die ganze Gruppe vollständig.",
            Features = ["inspect-item", "selected-item-stock", "set-item-stock"], ChangesSaveData = true,
            Start = ctx => GiveItems(ctx, [(Megalixir, "Megalixir")], ctx.Amount),
        },
        new()
        {
            Key = "mystery-gift", Category = RewardCategory.Help, Cost = 750,
            Title = "Mystery Gift", TitleDe = "Überraschungsgeschenk",
            Prompt = "A random item, from a plain Potion to a rare Megalixir. Good luck!",
            PromptDe = "Ein zufälliges Item, vom einfachen Trank bis zum seltenen Megalixier. Viel Glück!",
            Features = ["inspect-item", "selected-item-stock", "set-item-stock"], ChangesSaveData = true,
            Start = MysteryGift,
        },
        new()
        {
            Key = "munny-gift", Category = RewardCategory.Help, Cost = 1000, Amount = 1000, AmountLabel = "munny", AmountLabelDe = "Munny",
            Title = "Munny Donation", TitleDe = "Munny-Spende",
            Prompt = "Gives Sora a pile of munny.",
            PromptDe = "Schenkt Sora einen Haufen Munny.",
            Features = ["munny"], ChangesSaveData = true,
            Check = ctx => ctx.Read("munny") switch
            {
                null => Readiness.Wait("Waiting for the save data."),
                >= 999999 => Readiness.Reject("Sora already has the maximum munny."),
                _ => Readiness.Ready,
            },
            Start = async ctx =>
            {
                double current = ctx.Read("munny") ?? 0, target = Math.Min(999999, current + ctx.Amount);
                await ctx.RunAsync("munny", target);
                ctx.Detail = $"+{N(target - current)} munny";
            },
        },
        new()
        {
            Key = "exp-gift", Category = RewardCategory.Help, Cost = 2500, Amount = 1000, AmountLabel = "EXP", AmountLabelDe = "EXP", MaxAmount = 9999999,
            Title = "EXP Gift", TitleDe = "EXP-Geschenk",
            Prompt = "Gives Sora experience. Level-ups and their rewards apply.",
            PromptDe = "Schenkt Sora Erfahrung. Level-ups samt Belohnungen inklusive.",
            Features = ["add-experience"], ChangesSaveData = true,
            Start = async ctx => { await ctx.RunAsync("add-experience", ctx.Amount); ctx.Detail = $"+{N(ctx.Amount)} EXP"; },
        },
        new()
        {
            Key = "power-boost", Category = RewardCategory.Help, Cost = 10000, Amount = 1, AmountLabel = "Strength", AmountLabelDe = "Stärke", MaxAmount = 100,
            Title = "Strength +1 (permanent)", TitleDe = "Stärke +1 (dauerhaft)",
            Prompt = "Raises Sora's Strength permanently.",
            PromptDe = "Erhöht Soras Stärke dauerhaft.",
            Features = ["boost.strength.add"], ChangesSaveData = true,
            Start = async ctx => { await ctx.RunAsync("boost.strength.add", ctx.Amount); ctx.Detail = $"+{ctx.Amount} Strength"; },
        },
        Values("regen", RewardCategory.Help, 3000, 60, "regen", "Regeneration", "Regeneration",
            "The controlled character's HP refills constantly for a while.", "Die HP der gesteuerten Figur füllen sich eine Weile lang ständig auf.",
            ("combat.autoheal", 1)),
        Values("infinite-mp", RewardCategory.Help, 2000, 60, "mp", "Unlimited MP", "Unendlich MP",
            "Keeps the controlled character's MP full for a while. Requires an MP gauge.", "Hält die MP der gesteuerten Figur eine Weile lang voll. Benötigt eine MP-Leiste.",
            ("combat.fullmp", 1)),
        new()
        {
            Key = "invincible", Category = RewardCategory.Help, Cost = 5000, DurationSeconds = 30, Group = "defense",
            AllowedRoles = EffectPlayerRoles.FieldPlayers,
            Title = "Invincibility", TitleDe = "Unverwundbar",
            Prompt = "Blocks normal HP damage to the controlled character. Time counts only while protection is confirmed; scripted HP changes can bypass it.",
            PromptDe = "Blockiert normalen HP-Schaden an der gesteuerten Figur. Die Zeit zählt nur bei bestätigtem Schutz; direkte HP-Änderungen durch Skripte können ihn umgehen.",
            Features = ["player_damage_guard", "combat.damage_guard_owned"],
            Check = ctx => ctx.DamageGuardStartReadiness,
            ActiveCheck = ctx => ctx.DamageGuardActiveReadiness,
            Start = ctx => ctx.StartDamageGuardAsync(),
        },
        new()
        {
            Key = "lucky-streak", Category = RewardCategory.Help, Cost = 2000, DurationSeconds = 120, Group = "loot",
            Title = "Lucky Streak", TitleDe = "Glückssträhne",
            Prompt = "More munny, orbs and item drops for a while.",
            PromptDe = "Eine Weile lang mehr Munny, Kugeln und Item-Drops.",
            Features = ["loot.jackpot", "loot.lucky"],
            Start = async ctx =>
            {
                await ctx.SetAsync("loot.jackpot", (ctx.Read("loot.jackpot") ?? 0) + 3);
                await ctx.SetAsync("loot.lucky", (ctx.Read("loot.lucky") ?? 0) + 20);
            },
        },
        new()
        {
            Key = "magnet", Category = RewardCategory.Help, Cost = 1000, DurationSeconds = 120, Group = "draw",
            Title = "Orb Magnet", TitleDe = "Kugelmagnet",
            Prompt = "Pulls in orbs from far away for a while.",
            PromptDe = "Zieht eine Weile lang Kugeln aus großer Entfernung an.",
            Features = ["loot.draw"],
            Start = ctx => ctx.SetAsync("loot.draw", Math.Max(ctx.Read("loot.draw") ?? 0, 1500)),
        },
        new()
        {
            Key = "super-speed", Category = RewardCategory.Help, Cost = 1500, DurationSeconds = 45, Group = "speed",
            Title = "Super Speed", TitleDe = "Supertempo",
            Prompt = "The controlled character runs much faster for a while.",
            PromptDe = "Die gesteuerte Figur rennt eine Weile lang viel schneller.",
            AllowedRoles = EffectPlayerRoles.FieldPlayers,
            Features = ["movement.run_speed", "movement.walk_speed"],
            Check = ctx => ctx.MovementStartReadiness(MovementMask.Speed),
            ActiveCheck = ctx => ctx.MovementActiveReadiness,
            Start = ctx => ctx.StartMovementAsync(MovementMask.Speed, v => MovementValues.FromValues(
                Math.Clamp(v.Value(0) * 2.5f, 0, 32), Math.Clamp(v.Value(1) * 2.5f, 0, 64), 0, 0)),
        },
        LockOnPair("eagle-eye", RewardCategory.Help, 500, 120, "Eagle Eye", "Adlerauge",
            "Lock-on reaches enemies far away for a while.", "Lock-on erreicht eine Weile lang weit entfernte Gegner.",
            4f),
        new()
        {
            // The factor belongs to that enemy; it cannot be taken back once lock-on moves on, so it lasts for the enemy's life.
            Key = "enemy-glass-cannon", Category = RewardCategory.Help, Cost = 3000, MaxWaitSeconds = 120,
            Title = "Weaken the Enemy", TitleDe = "Gegner schwächen",
            Prompt = "The enemy Sora has locked on to takes 2.5x damage from now on. Waits for a manual lock-on.",
            PromptDe = "Der anvisierte Gegner nimmt ab jetzt 2,5-fachen Schaden. Wartet auf ein manuelles Lock-on.",
            Features = ["damage.target.general", "target_lock_mode", "target_hp"],
            Check = ctx =>
            {
                var locked = TargetLocked(ctx);
                if (locked.Kind != ReadinessKind.Ready) return locked;
                return ctx.Read("damage.target.general") is >= 250 ? Readiness.Reject("This enemy is already weakened.") : Readiness.Ready;
            },
            Start = ctx => ctx.RunAsync("damage.target.general", 250),
        },
        Form("valor", 1, RewardCategory.Help, 2000, 45, "Valor Form", "Mut-Form"),
        Form("wisdom", 2, RewardCategory.Help, 2000, 45, "Wisdom Form", "Weisheits-Form"),
        Form("limit", 3, RewardCategory.Help, 2000, 45, "Limit Form", "Limit-Form"),
        Form("master", 4, RewardCategory.Help, 3000, 45, "Master Form", "Meister-Form"),
        Form("final", 5, RewardCategory.Help, 5000, 45, "Final Form", "Final-Form"),
        new()
        {
            Key = "gummi-repair", Category = RewardCategory.Help, Cost = 1000,
            RequiresPlayerControl = false,
            Title = "Repair Gummi Ship", TitleDe = "Gumi-Jet reparieren",
            Prompt = "Restores the Gummi Ship's HP. Gummi missions only; refunded elsewhere.",
            PromptDe = "Repariert den Gumi-Jet vollständig. Nur in Gumi-Missionen, sonst gibt es die Punkte zurück.",
            Features = ["gummi.refill", "gummi.hp", "gummi.max_hp"],
            Check = ctx =>
            {
                var mission = InGummiMission(ctx);
                if (mission.Kind != ReadinessKind.Ready) return mission;
                return Full(ctx, "gummi.hp", "gummi.max_hp") ? Readiness.Reject("The Gummi Ship is already fully repaired.") : Readiness.Ready;
            },
            Start = ctx => ctx.RunAsync("gummi.refill"),
        },
        new()
        {
            Key = "gummi-clear", Category = RewardCategory.Help, Cost = 500,
            RequiresPlayerControl = false,
            Title = "Clear Enemy Bullets", TitleDe = "Gegnerschüsse löschen",
            Prompt = "Removes the enemy bullets on screen. Gummi missions only; refunded elsewhere.",
            PromptDe = "Entfernt die Gegnerschüsse auf dem Bildschirm. Nur in Gumi-Missionen, sonst gibt es die Punkte zurück.",
            Features = ["gummi.projectiles.clear", "gummi.hp"],
            Check = InGummiMission,
            Start = ctx => ctx.RunAsync("gummi.projectiles.clear"),
        },

        // ---- Harmful ------------------------------------------------------------------------
        new()
        {
            Key = "one-hp", Category = RewardCategory.Harm, Cost = 5000,
            AllowedRoles = EffectPlayerRoles.FieldPlayers,
            Title = "One HP Left", TitleDe = "Nur noch 1 HP",
            Prompt = "Drops the controlled character to 1 HP. One hit and it's over...",
            PromptDe = "Setzt die gesteuerte Figur auf 1 HP. Ein Treffer und es ist vorbei...",
            Features = ["player.hp", "combat.autoheal"],
            Check = ctx =>
            {
                if (ctx.Read("player.hp") is <= 1) return Readiness.Reject("The current character already has 1 HP.");
                // Regeneration would refill the HP within a frame.
                return ctx.Read("combat.autoheal") == 1 ? Readiness.Wait("Waiting for Regeneration to end.") : Readiness.Ready;
            },
            Start = ctx => ctx.RunAsync("player.hp", 1),
        },
        new()
        {
            Key = "drain-drive", Category = RewardCategory.Harm, Cost = 1500,
            Title = "Drain Drive Gauge", TitleDe = "Drive-Leiste leeren",
            Prompt = "Empties every Drive bar. No forms for you.",
            PromptDe = "Leert alle Drive-Balken. Keine Formen mehr für dich.",
            Features = ["player.drive.bars", "player.drive.fraction", "player.form.id", "player.gauge.mode"],
            Check = ctx =>
            {
                if (InForm(ctx) || GaugeBusy(ctx)) return Readiness.Wait("Waiting for the Drive Form or summon to end.");
                return ctx.Read("player.drive.bars") is 0 && ctx.Read("player.drive.fraction") is null or 0
                    ? Readiness.Reject("The Drive gauge is already empty.") : Readiness.Ready;
            },
            Start = ctx => ctx.RunAsync("player.drive.bars", 0),
        },
        new()
        {
            Key = "pickpocket", Category = RewardCategory.Harm, Cost = 1500, Amount = 500, AmountLabel = "munny", AmountLabelDe = "Munny",
            Title = "Pickpocket", TitleDe = "Taschendieb",
            Prompt = "Steals munny from Sora.",
            PromptDe = "Klaut Sora Munny.",
            Features = ["munny"], ChangesSaveData = true,
            Check = ctx => ctx.Read("munny") switch
            {
                null => Readiness.Wait("Waiting for the save data."),
                <= 0 => Readiness.Reject("Sora has no munny to steal."),
                _ => Readiness.Ready,
            },
            Start = async ctx =>
            {
                double current = ctx.Read("munny") ?? 0, target = Math.Max(0, current - ctx.Amount);
                await ctx.RunAsync("munny", target);
                ctx.Detail = $"-{N(current - target)} munny";
            },
        },
        new()
        {
            Key = "potion-thief", Category = RewardCategory.Harm, Cost = 2000, Amount = 3, AmountLabel = "of each", AmountLabelDe = "je Sorte", MaxAmount = 99,
            Title = "Potion Thief", TitleDe = "Trankdieb",
            Prompt = "Steals Potions, Hi-Potions and Ethers from Sora's bag.",
            PromptDe = "Klaut Tränke, Hi-Tränke und Äther aus Soras Tasche.",
            Features = ["inspect-item", "selected-item-stock", "set-item-stock"], ChangesSaveData = true,
            Start = async ctx =>
            {
                var stolen = new List<string>();
                foreach (var (id, name) in new[] { (Potion, "Potion"), (HiPotion, "Hi-Potion"), (Ether, "Ether") })
                {
                    try
                    {
                        int change = await ctx.AdjustItemAsync(id, -ctx.Amount);
                        if (change != 0) stolen.Add($"{change} {name}");
                    }
                    catch (Exception) when (stolen.Count > 0) { break; } // Keep what was already taken; that is what the viewer paid for.
                }
                if (stolen.Count == 0) throw new EffectRejectedException("Sora has nothing to steal.");
                ctx.Detail = string.Join(", ", stolen);
            },
        },
        new()
        {
            Key = "reload-room", Category = RewardCategory.Harm, Cost = 4000,
            Title = "Reload Room", TitleDe = "Raum neu laden",
            Prompt = "Reloads the current room: enemies come back and Sora returns to the entrance.",
            PromptDe = "Lädt den aktuellen Raum neu: Gegner kommen zurück und Sora steht wieder am Eingang.",
            Features = ["world.reload_room"], ChangesSaveData = true,
            Start = ctx => ctx.RunAsync("world.reload_room"),
        },
        new()
        {
            Key = "revert", Category = RewardCategory.Harm, Cost = 2500, Group = "form", Interrupts = true,
            Title = "Kick Out of Drive Form", TitleDe = "Raus aus der Drive-Form",
            Prompt = "Ends the current Drive Form immediately. Refunded if Sora is not in a form.",
            PromptDe = "Beendet die aktuelle Drive-Form sofort. Ohne Form gibt es die Punkte zurück.",
            Features = ["drive.revert", "player.form.id", "drive.phase"],
            // Only checked when no Twitch form is running: then a revert in progress means Sora is already leaving the form.
            Check = ctx => !InForm(ctx) ? Readiness.Reject("Sora is not in a Drive Form.")
                : ctx.Read("drive.phase") == 3 ? Readiness.Reject("Sora is already leaving the Drive Form.")
                : ctx.Read("drive.phase") is > 0 ? Readiness.Wait("Waiting for the current Drive transformation to finish.") : Readiness.Ready,
            Start = ctx => ctx.RunAsync("drive.revert"),
        },
        new()
        {
            Key = "heal-enemy", Category = RewardCategory.Harm, Cost = 3000, MaxWaitSeconds = 120,
            Title = "Heal the Enemy", TitleDe = "Gegner heilen",
            Prompt = "Fully heals the enemy Sora has locked on to. Waits for a manual lock-on.",
            PromptDe = "Heilt den anvisierten Gegner vollständig. Wartet auf ein manuelles Lock-on.",
            Features = ["target_refill_hp", "target_lock_mode", "target_hp", "target_max_hp"],
            Check = ctx =>
            {
                var locked = TargetLocked(ctx);
                if (locked.Kind != ReadinessKind.Ready) return locked;
                return Full(ctx, "target_hp", "target_max_hp") ? Readiness.Reject("The enemy already has full HP.") : Readiness.Ready;
            },
            Start = ctx => ctx.RunAsync("target_refill_hp"),
        },
        new()
        {
            Key = "enrage-enemy", Category = RewardCategory.Harm, Cost = 1500, MaxWaitSeconds = 120,
            Title = "Enrage the Enemy", TitleDe = "Gegner wütend machen",
            Prompt = "Fills the locked enemy's revenge meter. Its next hit triggers a counterattack.",
            PromptDe = "Füllt die Revenge-Leiste des anvisierten Gegners. Der nächste Treffer löst seinen Konter aus.",
            Features = ["target_set_revenge", "target_lock_mode", "target_hp", "target_revenge_threshold"],
            Check = ctx =>
            {
                var locked = TargetLocked(ctx);
                if (locked.Kind != ReadinessKind.Ready) return locked;
                return ctx.Read("target_revenge_threshold") is > 0 ? Readiness.Ready : Readiness.Reject("This enemy has no revenge meter.");
            },
            Start = ctx => ctx.RunAsync("target_set_revenge", ctx.Read("target_revenge_threshold") ?? 0),
        },
        Values("glass-cannon", RewardCategory.Harm, 3000, 30, "defense", "Glass Cannon", "Glaskanone",
            "Sora takes 2.5x damage for a while.", "Sora nimmt eine Weile lang 2,5-fachen Schaden.",
            ("damage.player.general", 250)),
        Values("tax-collector", RewardCategory.Harm, 1000, 120, "loot", "Tax Collector", "Steuereintreiber",
            "Munny orbs turn into Drive orbs for a while.", "Munny-Kugeln werden eine Weile lang zu Drive-Kugeln.",
            ("loot.retained", 0)),
        new()
        {
            Key = "snail", Category = RewardCategory.Harm, Cost = 1500, DurationSeconds = 30, Group = "speed",
            Title = "Snail Mode", TitleDe = "Schneckenmodus",
            Prompt = "The controlled character moves at a snail's pace for a while.",
            PromptDe = "Die gesteuerte Figur bewegt sich eine Weile lang im Schneckentempo.",
            AllowedRoles = EffectPlayerRoles.FieldPlayers,
            Features = ["movement.run_speed", "movement.walk_speed"],
            Check = ctx => ctx.MovementStartReadiness(MovementMask.Speed),
            ActiveCheck = ctx => ctx.MovementActiveReadiness,
            Start = ctx => ctx.StartMovementAsync(MovementMask.Speed, v => MovementValues.FromValues(
                Math.Clamp(v.Value(0) * .25f, .5f, 32), Math.Clamp(v.Value(1) * .25f, 1, 64), 0, 0)),
        },
        Values("fast-forward", RewardCategory.Harm, 2000, 30, "time", "Fast Forward", "Vorspulen",
            "The whole game runs at double speed. Good luck dodging.", "Das ganze Spiel läuft doppelt so schnell. Viel Glück beim Ausweichen.",
            ("time.multiplier", 2)),
        LockOnPair("short-sighted", RewardCategory.Harm, 1000, 60, "Short-Sighted", "Kurzsichtig",
            "Lock-on only reaches enemies right next to Sora for a while.", "Lock-on erreicht eine Weile lang nur Gegner direkt neben Sora.",
            .15f),
        Form("antiform", 6, RewardCategory.Harm, 4000, 30, "Antiform", "Anti-Form",
            "Turns Sora into Antiform for a while. No healing, no items, pure chaos.",
            "Verwandelt Sora eine Weile lang in die Anti-Form. Keine Heilung, keine Items, nur Chaos."),

        // ---- Funny --------------------------------------------------------------------------
        new()
        {
            Key = "roulette", Category = RewardCategory.Funny, Cost = 2500, DurationSeconds = 45, Group = "form",
            Title = "Drive Roulette", TitleDe = "Drive-Roulette",
            Prompt = "A random Drive Form for a while. Antiform included!",
            PromptDe = "Eine Weile lang eine zufällige Drive-Form. Anti-Form inklusive!",
            Features = FormFeatures,
            Check = FormCheck,
            Start = ctx => StartForm(ctx, ctx.Random.Next(1, 7)),
            Monitor = FormMonitor,
            End = EndForm,
            CancelPending = ctx => ctx.CancelDriveQueueAsync(),
        },
        new()
        {
            Key = "moon-jump", Category = RewardCategory.Funny, Cost = 1000, DurationSeconds = 45, Group = "jump",
            Title = "Moon Jump", TitleDe = "Mondsprung",
            Prompt = "Raises the controlled character's base jump height and limits falling speed. Gravity is unchanged; High Jump and special actions may use different values.",
            PromptDe = "Erhöht die Basis-Sprunghöhe der gesteuerten Figur und begrenzt das Falltempo. Die Schwerkraft bleibt gleich; Sportsfreund und Spezialaktionen können andere Werte verwenden.",
            AllowedRoles = EffectPlayerRoles.FieldPlayers,
            Features = ["movement.base_jump_height", "movement.fall_speed"],
            Check = ctx => ctx.MovementStartReadiness(MovementMask.Air),
            ActiveCheck = ctx => ctx.MovementActiveReadiness,
            Start = ctx => ctx.StartMovementAsync(MovementMask.Air, v => MovementValues.FromValues(0, 0, 3, Math.Clamp(v.Value(3) * 4, 0, 1000))),
        },
        Values("slow-mo", RewardCategory.Funny, 1500, 30, "time", "Slow Motion", "Zeitlupe",
            "The whole game runs at half speed for a while.", "Das ganze Spiel läuft eine Weile lang mit halber Geschwindigkeit.",
            ("time.multiplier", 0.5)),
        Fov("fisheye", 750, 60, 120, "Fisheye", "Fischauge",
            "Ultra-wide field of view for a while.", "Eine Weile lang ein extrem weites Sichtfeld."),
        Fov("tunnel-vision", 750, 45, 30, "Tunnel Vision", "Tunnelblick",
            "A narrow, zoomed-in view for a while.", "Eine Weile lang ein enges, herangezoomtes Sichtfeld."),
        new()
        {
            Key = "camera-glitch", Category = RewardCategory.Funny, Cost = 2500, DurationSeconds = 15, Group = "camera",
            Title = "Upside-Down Camera", TitleDe = "Kamera auf dem Kopf",
            Prompt = "The camera freezes in place and flips upside down for a few seconds.",
            PromptDe = "Die Kamera bleibt ein paar Sekunden stehen und steht kopf.",
            Features = ["camera.free", "camera.roll"],
            Start = async ctx => { await ctx.SetAsync("camera.free", 1, sustain: false); await ctx.SetAsync("camera.roll", 180, sustain: false); },
        },
        Animation("slowpoke", 1500, 0.4, "Slowpoke Animations", "Lahme Animationen",
            "Sora's animations and attacks play at 40% speed for a while.", "Soras Animationen und Angriffe laufen eine Weile lang mit 40 % Tempo."),
        Animation("hyper", 1500, 2, "Hyperactive Sora", "Hyperaktiver Sora",
            "Sora's animations and attacks play at double speed for a while.", "Soras Animationen und Angriffe laufen eine Weile lang doppelt so schnell."),
        new()
        {
            Key = "color-chaos", Category = RewardCategory.Funny, Cost = 1000, DurationSeconds = 60, Group = "display",
            AllowedRoles = EffectPlayerRoles.FieldPlayers,
            Title = "Color Chaos", TitleDe = "Farbchaos",
            Prompt = "A random color-vision filter at full strength for a while.",
            PromptDe = "Eine Weile lang ein zufälliger Farbsehfilter in voller Stärke.",
            Features = ["display.color_compare_apply", "display.color_state"],
            Check = ctx => TryColorState(ctx, out _, out _) ? Readiness.Ready : Readiness.Wait("Waiting for the current color filter"),
            Start = StartColorChaos,
            End = EndColorChaos,
        },
        Values("silence", RewardCategory.Funny, 500, 90, "music", "Silence!", "Ruhe!",
            "Mutes the music for a while.", "Schaltet die Musik eine Weile lang stumm.",
            ("audio.music", 0)),
        new()
        {
            Key = "ghost-walk", Category = RewardCategory.Funny, Cost = 2000, DurationSeconds = 12, Group = "position",
            Title = "Ghost Walk", TitleDe = "Geistermodus",
            Prompt = "Sora walks through walls briefly, then returns to the starting point if the saved character and scene are still valid.",
            PromptDe = "Sora läuft kurz durch Wände und kehrt zum Startpunkt zurück, solange die gespeicherte Figur und Szene noch gültig sind.",
            Features = ["player.position.bookmark", "player.position.return", "combat.movementcollision", "drive.phase"],
            Check = NoDriveTransition,
            Start = async ctx =>
            {
                await ctx.RunAsync("player.position.bookmark");
                await ctx.SetAsync("combat.movementcollision", 1, sustain: false);
            },
            End = async ctx =>
            {
                // The native bookmark validates the captured Actor lifetime and scene.
                // A rejected return must never be bypassed with raw coordinates or a reload.
                bool back = await TryRunAsync(ctx, "player.position.return");
                if (!back) ctx.Detail = "Return skipped: the saved position is no longer available.";
                await ctx.RestoreAsync();
            },
        },
        new()
        {
            Key = "hacker-mode", Category = RewardCategory.Funny, Cost = 500, DurationSeconds = 10, Group = "debug",
            Title = "Hacker Mode", TitleDe = "Hackermodus",
            Prompt = "Opens the game's hidden developer desktop for a few seconds.",
            PromptDe = "Öffnet für ein paar Sekunden den versteckten Entwickler-Desktop des Spiels.",
            Features = ["developer.show", "developer.hide"],
            Start = ctx => ctx.RunAsync("developer.show"),
            End = ctx => ctx.RunAsync("developer.hide"),
        },

        // ---- Annoying -----------------------------------------------------------------------
        Values("time-stop", RewardCategory.Annoying, 2000, 5, "freeze", "Time Stop", "Zeitstopp",
            "Freezes every character and effect for a few seconds.", "Friert alle Figuren und Effekte für ein paar Sekunden ein.",
            ("time.actor_effect_freeze", 1), sustain: false),
        Values("freeze-frame", RewardCategory.Annoying, 1500, 5, "freeze", "Freeze Frame", "Standbild",
            "The game freezes on the current image for a few seconds. Did it crash?", "Das Spiel bleibt ein paar Sekunden auf dem aktuellen Bild stehen. Abgestürzt?",
            ("practice.field_pause", 1), sustain: false),
        new()
        {
            Key = "pause-menu", Category = RewardCategory.Annoying, Cost = 1000,
            Title = "Pause!", TitleDe = "Pause!",
            Prompt = "Opens the pause menu. Right now.",
            PromptDe = "Öffnet das Pausenmenü. Jetzt sofort.",
            Features = ["time.pause_menu"],
            Start = ctx => ctx.RunAsync("time.pause_menu"),
        },
        Brightness("lights-out", 1500, 30, -50, "Lights Out", "Licht aus",
            "Turns the brightness all the way down for a while.", "Dreht die Helligkeit eine Weile lang ganz herunter."),
        Brightness("flashbang", 1000, 8, 50, "Flashbang", "Blendgranate",
            "Maximum brightness for a few seconds. Sunglasses recommended.", "Ein paar Sekunden maximale Helligkeit. Sonnenbrille empfohlen."),
        new()
        {
            Key = "deja-vu", Category = RewardCategory.Annoying, Cost = 2500, DurationSeconds = 10, Group = "position",
            Title = "Déjà Vu", TitleDe = "Déjà-vu",
            Prompt = "A few seconds later, Sora is pulled back to the exact same spot. Refunded if that is not possible.",
            PromptDe = "Ein paar Sekunden später wird Sora genau an dieselbe Stelle zurückgezogen. Klappt das nicht, gibt es die Punkte zurück.",
            Features = ["player.position.bookmark", "player.position.return", "drive.phase"],
            ChargeAfterEnd = true,
            Check = NoDriveTransition,
            Start = ctx => ctx.RunAsync("player.position.bookmark"),
            End = ctx => ctx.RunAsync("player.position.return"),
        },
        Values("mute-voices", RewardCategory.Annoying, 500, 90, "voice", "Who Said That?", "Wer hat das gesagt?",
            "Mutes every voice for a while.", "Schaltet alle Stimmen eine Weile lang stumm.",
            ("audio.voice", 0)),
        Values("no-subtitles", RewardCategory.Annoying, 300, 300, "captions", "No Subtitles", "Keine Untertitel",
            "Hides the captions for a while.", "Blendet die Untertitel eine Weile lang aus.",
            ("render.hide_captions", 1)),
    ];

    // ---- Builders ---------------------------------------------------------------------------

    /// <summary>A timed effect that sets values and restores them at the end.</summary>
    private static EffectDefinition Values(string key, RewardCategory category, int cost, int duration, string group,
        string title, string titleDe, string prompt, string promptDe, (string Feature, double Value) value, bool sustain = true) => new()
    {
        Key = key, Category = category, Cost = cost, DurationSeconds = duration, Group = group,
        Title = title, TitleDe = titleDe, Prompt = prompt, PromptDe = promptDe,
        Features = value.Feature == "combat.fullmp" ? [value.Feature, "player.mp.max"] : [value.Feature],
        AllowedRoles = value.Feature is "audio.music" or "audio.voice" or "render.hide_captions" or "combat.autoheal" or "combat.fullmp"
            ? EffectPlayerRoles.FieldPlayers : EffectPlayerRoles.Sora,
        SelfPauseFeature = value.Feature is "practice.field_pause" or "time.actor_effect_freeze" ? value.Feature : null,
        SelfPauseBlocker = value.Feature switch
        {
            "practice.field_pause" => GameplayBlockers.TrainerFieldPause,
            "time.actor_effect_freeze" => GameplayBlockers.TrainerActorFreeze,
            _ => GameplayBlockers.None
        },
        // The streamer may already have it on; then the redemption would change nothing.
        Check = ctx =>
        {
            if (value.Feature == "combat.fullmp")
            {
                var gauge = MpGauge(ctx, rejectNoGauge: true);
                if (gauge.Kind != ReadinessKind.Ready) return gauge;
            }
            return ctx.Read(value.Feature) is double current && EffectContext.Near(current, value.Value)
                ? Readiness.Reject($"{title} is already active.") : Readiness.Ready;
        },
        ActiveCheck = value.Feature == "combat.fullmp" ? ctx =>
            !ctx.Supports(value.Feature) ? Readiness.Wait("Waiting until Unlimited MP is available.") : MpGauge(ctx, rejectNoGauge: false) : null,
        Start = ctx => ctx.SetAsync(value.Feature, value.Value, sustain: sustain),
    };

    private static Readiness MpGauge(EffectContext ctx, bool rejectNoGauge)
    {
        // PlayerLiving bounds native STATUS+388 to an integer in 0..255. A zero gauge
        // is valid but cannot benefit from MP-only rewards. Unknown/invalid data waits.
        if (!ctx.Supports("player.mp.max") || ctx.Read("player.mp.max") is not double maximum ||
            maximum < 0 || maximum > 255 || maximum != Math.Truncate(maximum))
            return Readiness.Wait("Waiting for the current character's MP gauge.");
        if (maximum == 0)
            return rejectNoGauge ? Readiness.Reject("The current character has no MP gauge.") :
                Readiness.Wait("Paused until the current character has an MP gauge.");
        return Readiness.Ready;
    }

    private static EffectDefinition Form(string key, int form, RewardCategory category, int cost, int duration, string name, string nameDe,
        string? prompt = null, string? promptDe = null) => new()
    {
        Key = key, Category = category, Cost = cost, DurationSeconds = duration, Group = "form",
        Title = category == RewardCategory.Harm ? name : "Drive: " + name,
        TitleDe = category == RewardCategory.Harm ? nameDe : "Drive: " + nameDe,
        Prompt = prompt ?? $"Sora transforms into {name} for a while.",
        PromptDe = promptDe ?? $"Sora verwandelt sich eine Weile lang in die {nameDe}.",
        Features = FormFeatures,
        Check = FormCheck,
        Start = ctx => StartForm(ctx, form),
        Monitor = FormMonitor,
        End = EndForm,
        CancelPending = ctx => ctx.CancelDriveQueueAsync(),
    };

    // A property, not a field: the catalog is built by a static initializer that runs before later fields are set.
    private static string[] FormFeatures =>
        ["drive.trigger", "drive.revert", "drive.cancel", "combat.formtimer", "player.form.id", "drive.phase", "drive.result", "drive.requested"];

    /// <summary>The bridge takes one Drive switch at a time; a queued form waits until the previous revert or transformation is done.</summary>
    private static Readiness FormCheck(EffectContext ctx) => NoDriveTransition(ctx);

    private static Readiness NoDriveTransition(EffectContext ctx) =>
        ctx.Read("drive.phase") is > 0 ? Readiness.Wait("Waiting for the current Drive transformation to finish.") : Readiness.Ready;

    private static async Task StartForm(EffectContext ctx, int form)
    {
        ctx.State["form"] = form;
        ctx.State["from"] = ctx.Read("player.form.id") ?? 0;
        ctx.State["resultBefore"] = ctx.Read("drive.result") ?? -1;
        ctx.State["requestedBefore"] = ctx.Read("drive.requested") ?? -1;
        ctx.Detail = FormNames[form];
        ctx.Established = false; // The timer starts once Sora has actually transformed.
        // Hold the form timer so the form lasts exactly as long as the reward says. From base form it is set
        // first (a refused transformation then changes nothing); in another form it would refill that form's
        // timer on every refused attempt, so it is set only after the switch was accepted.
        bool fromBase = ctx.State["from"] == 0;
        if (fromBase) await ctx.SetAsync("combat.formtimer", 1);
        await ctx.RunAsync("drive.trigger", form);
        if (!fromBase)
        {
            try { await ctx.SetAsync("combat.formtimer", 1); }
            catch (Exception) { ctx.Own("combat.formtimer", 1); } // The switch is under way; the engine re-applies the hold.
        }
        if (ctx.Read("drive.phase") is > 0 || ctx.Read("drive.result") == 1) ctx.State["busy"] = 1;
    }

    /// <summary>
    /// The form counts once the switch has finished on the target form. Sora may already be in that
    /// form (the bridge reverts first), so the form id alone proves nothing until the switch was seen running.
    /// </summary>
    private static EffectProgress FormMonitor(EffectContext ctx)
    {
        double target = ctx.State["form"];
        double? form = ctx.Read("player.form.id"), phase = ctx.Read("drive.phase"), result = ctx.Read("drive.result"), requested = ctx.Read("drive.requested");
        if (!ctx.Established)
        {
            if (phase is > 0 || result == 1) ctx.State["busy"] = 1;
            // Evidence that this switch ran: it was seen running, or its result or target changed (a short switch can fall between two polls).
            bool switched = ctx.State.ContainsKey("busy") || (result ?? -1) != ctx.State["resultBefore"] || (requested ?? -1) != ctx.State["requestedBefore"];
            bool onTarget = phase == 0 && form == target && (requested is null || requested == target) && result is null or 2;
            if (onTarget && (switched || ctx.State["from"] != target))
            {
                ctx.Established = true;
                return EffectProgress.Running;
            }
            if (switched && phase == 0 && result is >= 3 and <= 8) return EffectProgress.Failed("The game cancelled the transformation.");
            return ctx.SinceStart > TimeSpan.FromSeconds(30) ? EffectProgress.Failed("Sora could not transform right now.") : EffectProgress.Running;
        }
        if (!ctx.SceneReady || phase is > 0) return EffectProgress.Running;
        return form is double current && current != target ? EffectProgress.Ended("Sora left the form.") : EffectProgress.Running;
    }

    private static async Task EndForm(EffectContext ctx)
    {
        if (!ctx.Established)
        {
            // Still transforming: drop the trainer's pending steps (a native transition already running finishes).
            await ctx.CancelDriveQueueAsync();
            await ctx.RestoreAsync();
            return;
        }
        await ctx.RestoreAsync();
        // A replacing form reverts by itself, Kick Out already sent the revert, and a form the game ended needs nothing.
        if (ctx.EndReason is EndReason.Replaced or EndReason.Interrupted || ctx.Read("player.form.id") != ctx.State["form"]) return;
        await ctx.RunAsync("drive.revert");
    }

    /// <summary>
    /// Field of view: setting the FOV also enables the override, so the end disables the
    /// override again unless the streamer had their own FOV override active.
    /// </summary>
    private static EffectDefinition Fov(string key, int cost, int duration, double fov, string title, string titleDe, string prompt, string promptDe) => new()
    {
        Key = key, Category = RewardCategory.Funny, Cost = cost, DurationSeconds = duration, Group = "fov",
        Title = title, TitleDe = titleDe, Prompt = prompt, PromptDe = promptDe,
        Features = ["camera.fov", "camera.fov_enabled"],
        Start = async ctx =>
        {
            ctx.State["fovWasEnabled"] = ctx.Read("camera.fov_enabled") ?? throw new EffectDeferredException("Waiting for camera state");
            ctx.State["fovOriginal"] = ctx.Read("camera.fov") ?? throw new EffectDeferredException("Waiting for camera field of view");
            // Capture the switch before the FOV setter implicitly enables it. If the second
            // command fails, the normal owned-value cleanup can undo the first command.
            await ctx.SetAsync("camera.fov_enabled", 1);
            await ctx.SetAsync("camera.fov", fov);
        },
        End = async ctx =>
        {
            double enabled = ctx.Read("camera.fov_enabled") ?? throw new EffectDeferredException("Waiting for camera state before restoring");
            if (enabled == 0) { ctx.AbandonRestores(); return; } // The native lease or the streamer's override already ended.
            double current = ctx.Read("camera.fov") ?? throw new EffectDeferredException("Waiting for camera field of view before restoring");
            if (!EffectContext.Near(current, fov)) { ctx.AbandonRestores(); return; } // Someone else changed it.
            try
            {
                if (ctx.State["fovWasEnabled"] != 0) await ctx.RunAsync("camera.fov", ctx.State["fovOriginal"]);
                else await ctx.RunAsync("camera.fov_enabled", 0);
            }
            catch (Exception error) { throw new EffectDeferredException("Camera restore is still pending: " + error.Message); }
            ctx.AbandonRestores();
        },
    };

    private static EffectDefinition Animation(string key, int cost, double speed, string title, string titleDe, string prompt, string promptDe) => new()
    {
        Key = key, Category = RewardCategory.Funny, Cost = cost, DurationSeconds = 30, Group = "anim",
        Title = title, TitleDe = titleDe, Prompt = prompt, PromptDe = promptDe,
        Features = ["motion.speed", "motion.override"],
        Start = async ctx => { await ctx.SetAsync("motion.speed", speed, sustain: false); await ctx.SetAsync("motion.override", 1); },
    };

    private static EffectDefinition Brightness(string key, int cost, int duration, double level, string title, string titleDe, string prompt, string promptDe) => new()
    {
        Key = key, Category = RewardCategory.Annoying, Cost = cost, DurationSeconds = duration, Group = "display",
        AllowedRoles = EffectPlayerRoles.FieldPlayers,
        Title = title, TitleDe = titleDe, Prompt = prompt, PromptDe = promptDe,
        Features = ["display.brightness_preview"],
        Start = ctx => ctx.SetAsync("display.brightness_preview", level),
    };

    // ---- Helpers ----------------------------------------------------------------------------

    private static EffectDefinition LockOnPair(string key, RewardCategory category, int cost, int duration,
        string title, string titleDe, string prompt, string promptDe, float scale) => new()
    {
        Key = key, Category = category, Cost = cost, DurationSeconds = duration, Group = "targeting",
        Title = title, TitleDe = titleDe, Prompt = prompt, PromptDe = promptDe,
        Features = ["targeting.pair_compare_apply", "targeting.pair_break_bits", "targeting.default_break_distance"],
        Check = ctx => ctx.LockOnStartReadiness(scale), ActiveCheck = ctx => ctx.LockOnActiveReadiness,
        Start = ctx => ctx.StartLockOnPairAsync(scale), Monitor = ctx => ctx.LockOnProgress,
    };

    private static bool TryColorState(EffectContext ctx, out int mode, out int severity)
    {
        mode = severity = 0;
        if (ctx.Read("display.color_state") is not double packed || packed < 0 || packed > 58 || Math.Truncate(packed) != packed) return false;
        mode = (int)packed / 16; severity = (int)packed % 16;
        return mode is >= 0 and <= 3 && (mode == 0 ? severity == 0 : severity is >= 1 and <= 10);
    }

    private static async Task StartColorChaos(EffectContext ctx)
    {
        if (!TryColorState(ctx, out int originalMode, out int originalSeverity))
            throw new EffectDeferredException("Waiting for the current color filter");
        // Do not charge for applying a full-strength filter that was already selected.
        int[] choices = Enumerable.Range(1, 3).Where(m => originalSeverity != 10 || m != originalMode).ToArray();
        int mode = choices[ctx.Random.Next(choices.Length)];
        await ctx.RunAsync("display.color_compare_apply", 0, originalMode, originalSeverity, mode, 10);
        ctx.State["colorOriginalMode"] = originalMode; ctx.State["colorOriginalSeverity"] = originalSeverity;
        ctx.State["colorAppliedMode"] = mode; ctx.State["colorOwned"] = 1;
        ctx.Detail = $"Filter {mode}";
    }

    private static async Task EndColorChaos(EffectContext ctx)
    {
        if (ctx.State.GetValueOrDefault("colorOwned") != 1) return;
        try
        {
            // The native action compares the complete pair under the presentation mutex.
            // A changed pair is a successful no-op, including changes after the last snapshot.
            await ctx.RunAsync("display.color_compare_apply", 1, ctx.State["colorAppliedMode"], 10,
                ctx.State["colorOriginalMode"], ctx.State["colorOriginalSeverity"]);
        }
        catch (Exception error) { throw new EffectDeferredException("Color-filter restore is still pending: " + error.Message); }
        ctx.State["colorOwned"] = 0;
    }

    private static bool Full(EffectContext ctx, string value, string maximum) =>
        ctx.Read(value) is double current && ctx.Read(maximum) is double max && max > 0 && current >= max;

    private static bool InForm(EffectContext ctx) => ctx.Read("player.form.id") is double form && form != 0;

    /// <summary>The Drive gauge shows a form or summon timer instead of Drive bars.</summary>
    private static bool GaugeBusy(EffectContext ctx) => ctx.Read("player.gauge.mode") is 2 or 3;

    private static string N(double value) => value.ToString("N0", CultureInfo.InvariantCulture);

    private static Readiness TargetLocked(EffectContext ctx) =>
        ctx.Read("target_lock_mode") == 2 && ctx.Read("target_hp") is > 0
            ? Readiness.Ready
            : Readiness.Wait("Waiting for Sora to lock on to an enemy.");

    private static Readiness InGummiMission(EffectContext ctx) =>
        ctx.Read("gummi.hp") is not null ? Readiness.Ready : Readiness.Reject("Only works during a Gummi Ship mission.");

    /// <summary>Best effort: the scene may have changed in the meantime. Returns whether the game accepted it.</summary>
    private static async Task<bool> TryRunAsync(EffectContext ctx, string featureId, params double[] arguments)
    {
        try { await ctx.RunAsync(featureId, arguments); return true; }
        catch (EffectDeferredException) { throw; }
        catch (Exception) when (ctx.ControlReadiness().Kind != ReadinessKind.Ready)
        { throw new EffectDeferredException("The game became unavailable before cleanup completed"); }
        catch (Exception) { return false; }
    }

    private static async Task GiveItems(EffectContext ctx, (int Id, string Name)[] items, int amount)
    {
        var given = new List<string>();
        foreach (var (id, name) in items)
        {
            try
            {
                int change = await ctx.AdjustItemAsync(id, amount);
                if (change > 0) given.Add($"+{change} {name}");
            }
            catch (Exception) when (given.Count > 0) { break; } // Keep what was already given; that is what the viewer paid for.
        }
        if (given.Count == 0) throw new EffectRejectedException("Sora's bag has no room for these items.");
        ctx.Detail = string.Join(", ", given);
    }

    private static async Task MysteryGift(EffectContext ctx)
    {
        var candidates = MysteryItems.ToList();
        while (candidates.Count > 0)
        {
            int roll = ctx.Random.Next(candidates.Sum(c => c.Weight));
            var item = candidates.First(c => (roll -= c.Weight) < 0);
            if (await ctx.AdjustItemAsync(item.Id, 1) > 0) { ctx.Detail = item.Name; return; }
            candidates.Remove(item); // That item is full; roll again among the rest.
        }
        throw new EffectRejectedException("Sora's bag is full.");
    }
}
