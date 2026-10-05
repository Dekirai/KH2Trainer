using System.IO;
using System.Runtime.CompilerServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Markup;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using System.Xml.Linq;
using KH2Trainer;
using KH2Trainer.Core;

internal static class FeatureCardUiChecks
{
    public static object Run(string output, Application app)
    {
        Directory.CreateDirectory(output);
        using var source = typeof(FeatureVm).Assembly.GetManifestResourceStream("KH2Trainer.Data.features.json")
            ?? throw new InvalidDataException("Embedded feature catalog missing.");
        var catalog = FeatureCatalog.Load(source).Where(f => f.CapabilitySlot is >= 392 and <= 418 or >= 424 and <= 438 or >= 447 and <= 455).ToArray();
        int checks = 0;
        void Check(bool value, string message) { ++checks; if (!value) throw new InvalidDataException(message); }
        Check(catalog.Length == 51, "The renderer, audio, editor, window and MSAA feature cards are incomplete.");

        // Parse the actual application's card template, copied by MSBuild. This
        // creates only a DataTemplate: no Window constructor or Startup handler.
        XNamespace ns = "http://schemas.microsoft.com/winfx/2006/xaml/presentation";
        var document = XDocument.Load(Path.Combine(AppContext.BaseDirectory, "FeatureCards.Source.xaml"));
        var templateXml = document.Descendants(ns + "ItemsControl")
            .Single(e => (string?)e.Attribute("ItemsSource") == "{Binding VisibleFeatures}")
            .Element(ns + "ItemsControl.ItemTemplate")!.Element(ns + "DataTemplate")!;
        var template = (DataTemplate)XamlReader.Parse(templateXml.ToString());

        // FeatureVm's rendering path needs only an owner reference. Bypassing the
        // owner constructor avoids process discovery, timers and user folders.
        // No Apply command is executed; these are presentation-only fixtures.
        var owner = (MainViewModel)RuntimeHelpers.GetUninitializedObject(typeof(MainViewModel));
        var cards = catalog.Select(f => new FeatureVm(f, owner, new Dictionary<string, IReadOnlyList<FeatureChoice>>())).ToArray();
        var snapshot = new TrainerSnapshot { Connected = true, Status = 1 };
        foreach (var card in cards)
        {
            int slot = card.Definition.CapabilitySlot;
            snapshot.Supported[slot / 64] |= 1UL << (slot % 64);
            card.Update(snapshot);
            Check(card.LiveValue == "—", "Unavailable values must not appear as measured zero: " + card.Name);
            if (card.Definition.ValueSlot >= 0)
            {
                int valueSlot = card.Definition.ValueSlot;
                snapshot.Valid[valueSlot / 64] |= 1UL << (valueSlot % 64);
                card.Update(snapshot);
                Check(card.LiveValue != "—", "A valid zero disappeared: " + card.Name);
                snapshot.Valid[valueSlot / 64] &= ~(1UL << (valueSlot % 64));
            }
            Check(card.IsEditable == (slot is 424 or 425 or 431 or 432 or 447 or 448), "Unexpected feature editability: " + card.Name);
        }
        foreach (var card in cards.Where(c => c.Definition.ValueSlot >= 0))
        {
            int slot = card.Definition.ValueSlot;
            snapshot.Valid[slot / 64] |= 1UL << (slot % 64);
            snapshot.Values[slot] = slot switch
            {
                392 => 8.456, 393 => 0.032, 394 => 0.004, 395 => 11.67,
                396 => 4, 397 => 8, 398 or 400 => 3840, 399 or 401 => 2160,
                402 => 512, 403 => 2048, 404 => 2,
                405 or 406 or 407 => 64, 408 => 1, 409 => 3, 410 => 16,
                411 => 5, 412 => 2, 413 => 4294967295, 414 => 3, 415 => 4294967295,
                416 => -12345.678, 417 => 0, 418 => 98765.432,
                425 or 427 => 60, 426 => 4, 428 => -30, 429 => 180, 430 => 0,
                433 => 1920, 434 => 1080, 435 => 2, 436 => 1, 437 => 1600, 438 => 900,
                449 => 1, 450 => 4, 451 => 8, 452 => 4, 453 => 2, 454 => 4, 455 => 1, _ => 0
            };
            card.Update(snapshot);
        }
        Check(cards.Single(c => c.Definition.CapabilitySlot == 408).LiveValue == "Available", "Audio readiness needs a readable label.");
        Check(cards.Single(c => c.Definition.CapabilitySlot == 414).LiveValue == "Line", "Listener kind needs a readable label.");
        Check(cards.Single(c => c.Definition.CapabilitySlot == 426).LiveValue == "Preview", "Editor phase needs a readable label.");
        Check(cards.Single(c => c.Definition.CapabilitySlot == 435).LiveValue == "Maximized", "Window mode needs a readable label.");
        Check(cards.Single(c => c.Definition.CapabilitySlot == 436).LiveValue == "Pending", "Queued resize must be distinguished from completion.");
        Check(cards.Single(c => c.Definition.CapabilitySlot == 449).LiveValue == "Fixed", "MSAA policy mode needs a readable label.");
        Check(cards.Single(c => c.Definition.CapabilitySlot == 455).LiveValue == "Resident", "Installed MSAA dispatch needs a readable status.");
        Check(cards.Single(c => c.Definition.CapabilitySlot == 415).LiveValue.StartsWith("4294967295", StringComparison.Ordinal),
            "Unsigned listener priority must not become negative or lose precision.");

        var renders = new List<object>();
        foreach (var group in cards.GroupBy(c => c.Definition.Category))
        {
            var panel = new StackPanel();
            panel.Children.Add(new TextBlock { Text = group.Key, FontSize = 30, FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 0, 0, 20) });
            var wrap = new WrapPanel(); panel.Children.Add(wrap);
            foreach (var card in group)
            {
                var element = (FrameworkElement)template.LoadContent(); element.DataContext = card; wrap.Children.Add(element);
            }
            var root = new Border { Background = (Brush)app.Resources["BackgroundBrush"], Padding = new Thickness(24), Child = panel };
            root.SetValue(TextElement.ForegroundProperty, app.Resources["TextBrush"]);
            root.SetValue(TextElement.FontFamilyProperty, new FontFamily("Segoe UI")); root.SetValue(TextElement.FontSizeProperty, 14.0);
            double height = Layout(root);
            Check(height > 200 && height < 12000, "Invalid feature-card page height.");
            foreach (FrameworkElement element in wrap.Children)
            {
                var card = (FeatureVm)element.DataContext;
                var texts = Descendants<TextBlock>(element).Select(t => t.Text).ToArray();
                Check(texts.Contains(card.Name) && texts.Contains(card.Description) && texts.Contains(card.LiveValue),
                    "A feature lost its name, description or live-value binding: " + card.Name);
                var buttons = Descendants<Button>(element).Where(b => b.Visibility == Visibility.Visible).ToArray();
                Check(buttons.Length == (card.IsEditable ? 1 : 0), "Readouts must have no action button: " + card.Name);
            }
            var bitmap = new RenderTargetBitmap(780, (int)height, 96, 96, PixelFormats.Pbgra32); bitmap.Render(root);
            var pixels = new byte[bitmap.PixelWidth * bitmap.PixelHeight * 4]; bitmap.CopyPixels(pixels, bitmap.PixelWidth * 4, 0);
            int bright = 0; for (int i = 0; i < pixels.Length; i += 4) if (pixels[i] > 240 && pixels[i + 1] > 240 && pixels[i + 2] > 240) ++bright;
            Check(bright < bitmap.PixelWidth * bitmap.PixelHeight * .02, "Unexpected white feature-card background.");
            string name = group.Key.Replace(' ', '-').ToLowerInvariant() + ".png";
            var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
            using (var file = File.Create(Path.Combine(output, name))) encoder.Save(file);
            renders.Add(new { category = group.Key, width = 780, height, file = name });
        }
        foreach (var card in cards)
        {
            card.Update(TrainerSnapshot.Disconnected);
            Check(card.LiveValue == "—" && !card.ApplyCommand.CanExecute(null), "Disconnect retained a live value or action: " + card.Name);
        }
        return new { success = true, checks, features = cards.Length, renders, source = "Actual MainWindow feature DataTemplate and embedded catalog; synthetic snapshots only" };
    }

    private static double Layout(FrameworkElement element)
    {
        double previous = -1;
        for (int pass = 0; pass < 10; ++pass)
        {
            element.Dispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);
            element.Measure(new Size(780, double.PositiveInfinity));
            double height = Math.Ceiling(element.DesiredSize.Height);
            element.Arrange(new Rect(0, 0, 780, height)); element.UpdateLayout();
            if (height == previous && element.IsMeasureValid && element.IsArrangeValid) return height;
            previous = height;
        }
        throw new InvalidDataException("Feature-card layout did not stabilize.");
    }
    private static IEnumerable<T> Descendants<T>(DependencyObject root) where T : DependencyObject
    {
        for (int i = 0; i < VisualTreeHelper.GetChildrenCount(root); ++i)
        {
            var child = VisualTreeHelper.GetChild(root, i);
            if (child is T match) yield return match;
            foreach (var descendant in Descendants<T>(child)) yield return descendant;
        }
    }
}
