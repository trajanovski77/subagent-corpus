# Subagent specification baa32f0cbb97ddbf

## name
development-patterns

## description
Provides guidance on MVVM architecture patterns, Jetpack Compose UI development, and coding conventions for the Dash wallet project

## body
# Development Patterns

This app uses MVVM (ModelView ViewModel) as the primary design pattern.

The ViewModel class should be as follows.  It should have a UIState class for all data that is displayed
in the UI rather than having many Flows, one for each.

```Kotlin
data class GiftCardUIState(
    val giftCardId: String? = null,
    val error: Exception? = null,
    val status: String? = null,
    val queries: Int = 0
)

@HiltViewModel
class GiftCardDetailsViewModel @Inject constructor(
    private val applicationScope: CoroutineScope,
    private val giftCardDao: GiftCardDao,
    private val metadataProvider: TransactionMetadataProvider,
    private val analyticsService: AnalyticsService,
    private val repository: CTXSpendRepository,
    private val walletData: WalletDataProvider,
    private val ctxSpendConfig: CTXSpendConfig
) : ViewModel() {
    companion object {
        private val log = LoggerFactory.getLogger(GiftCardDetailsViewModel::class.java)
    }

    lateinit var transactionId: Sha256Hash
        private set
    private var tickerJob: Job? = null

    private var exchangeRate: ExchangeRate? = null
    private var retries = 3

    private val _uiState = MutableStateFlow(GiftCardUIState())
    val uiState: StateFlow<GiftCardUIState> = _uiState.asStateFlow()

    suspend fun performAction() {
        _uiState.value = GiftCardUIState(GiftCard("111"), null, "paid", 0)
    }
}
```
Rules for fields:
1. Asynchronously updated fields must be Flow (most of the time StateFlow) not LiveData
2. A private mutable state flow named starting with _ should be used internally in the class, while a immutable state should be created with asStateFlow on the private field

# UI

New user interfaces, whether new or updated, should use JetPack Compose.  Components such as buttons,
radio buttons, checkboxes and menu items should be keep in this folder:
```sh
../../common/src/main/java/org/dash/wallet/common/ui/components
```
Our Design System in Figma uses different names for components.  Here is a list that links the Figma
component to our component:

## Component Mapping from Figma to JetPack Compose in this project
- NavBar - use a named NavBar variant function (see NavBar section below); `TopNavBase` is the underlying base and remains available for full control
- top-intro - TopIntro
- menu - Menu
- menuitem - MenuItem
- btn - DashButton
- toggle - DashSwitch
- BottomSheet - ComposeBottomSheet
- feature.top.text - FeatureTopText
- feature.list - FeatureList
- feature.single.item - FeatureSingleItem
- Sheet/Buttons group - SheetButtonGroup
- ListX - ListItemX (numbered design-system variant, e.g. List1 → `ListItem1`); the general-purpose `ListItem` still covers ad-hoc combinations
- ListEmptyState - ListEmptyState
- tablelist-masternodekeys - TableListMasternodeKeyRow
- EnterAmount (input bar) - EnterAmount
- TextField-Base / text.field - TextField
- addressField - AddressField

## Dark Mode Compatibility

Every new screen, dialog, and component must work in both light and dark mode. The app uses `Theme.AppCompat.DayNight` which activates `values-night/` resource qualifiers automatically.

### Compose: The Golden Rule

**One call to `LocalDashColors.current` per composable, at the top. Never use `MyTheme.Colors.*` directly.**

```kotlin
@Composable
fun MyComponent(...) {
    val colors = LocalDashColors.current   // ← always this, nothing else
    Column(modifier = Modifier.background(colors.backgroundPrimary)) {
        Text("Hello", color = colors.textPrimary)
    }
}
```

**Root entry point wrapping** — The topmost composable in a Fragment's `setContent { }` block must be wrapped in `DashWalletTheme`:

```kotlin
composeView.setContent {
    DashWalletTheme {        // ← selects light or dark colors once
        MyScreen(...)
    }
}
```

**Rules:**
- `DashWalletTheme` wraps the root once. Child composables never call `isSystemInDarkTheme()`.
- `MyTheme.Colors` (light) and `MyTheme.DarkColors` (dark) are the source-of-truth instances; `LocalDashColors.current` resolves to the correct one automatically.
- Always wrap previews in `DashWalletTheme`. For dark previews add `uiMode = android.content.res.Configuration.UI_MODE_NIGHT_YES`:

```kotlin
@Preview(name = "Dark", uiMode = android.content.res.Configuration.UI_MODE_NIGHT_YES)
@Composable
fun MyPreviewDark() {
    DashWalletTheme { MyComponent(...) }
}
```

### ColorScheme Fields Reference

Key fields from `MyTheme.ColorScheme` (use via `LocalDashColors.current`):

| Field | Light | Dark | Use for |
|-------|-------|------|---------|
| `backgroundPrimary` | `#F5F6F7` | `#10151F` | Page background |
| `backgroundSecondary` | `#FFFFFF` | `#1D2532` | Cards, sheets, panels |
| `textPrimary` | `#191C1F` | `#FFFFFF` | Primary text |
| `textSecondary` | `#6E757C` | `#92929C` | Secondary / helper text |
| `textTertiary` | `#75808A` | `#75808A` | Tertiary / label text |
| `dashBlue` | `#008DE4` | `#008DE4` | Brand accent, links |
| `dividerColor` | `#EDF0F2` | `#2C3748` | Dividers, borders |
| `disabledButtonBg` | `#EEEEEE` | `#3C3C3C` | Disabled button background |
| `contentDisabled` | `#92929C` | `#92929C` | Disabled text / icon |

### XML Layouts: Semantic Color Tokens

Use semantic tokens from `values/colors.xml` — they have night overrides in `values-night/colors.xml`. Never use `@android:color/white` or literal hex values for surfaces or text.

| Purpose | Token |
|---------|-------|
| Page background | `@color/background_primary` |
| Card / sheet surface | `@color/background_secondary` |
| Primary text | `@color/content_primary` |
| Dividers / borders | `@color/divider_color` |

### XML Drawables: Adaptive Colors

- **Shape drawables** (cards, panels): fill with `@color/background_secondary`, not `@android:color/white`
- **Vector icons**: set `android:tint="@color/content_primary"` on the `<vector>` element instead of a hardcoded fill
- **Color state lists** (`<selector>`): the default (last) item must use `@color/content_primary`, not a hardcoded hex

### DashButton Disabled State

`DashButton` handles the disabled state automatically via `colors.disabledButtonBg` and `colors.contentDisabled`. Do not set `alpha` or override colors manually for disabled buttons — just pass `isEnabled = false`.

---

## NavBar / TopNavBase (Figma: NavBar)

The navigation bar lives in:
```
common/src/main/java/org/dash/wallet/common/ui/components/TopNavBase.kt
```

**Always use a named variant function** — they map 1-to-1 to the Figma NavBar playground variants and set the correct defaults automatically. `TopNavBase` is the base composable kept for full control and backward compatibility.

**Figma Design System node:** `6828-4232`

### Named variant functions

| Figma variant | Kotlin function | Leading | Centre | Trailing |
|---|---|---|---|---|
| NavBarBack | `NavBarBack` | ← chevron | — | — |
| NavBarBackTitle | `NavBarBackTitle` | ← chevron | title | — |
| NavBarBackTitleInfo | `NavBarBackTitleInfo` | ← chevron | title | ℹ bare icon (blue) |
| NavBarTitleClose | `NavBarTitleClose` | — | title | ✕ circle button |
| NavBarBackTitlePlus | `NavBarBackTitlePlus` | ← chevron | title | + circle button |
| NavBarBackPlus | `NavBarBackPlus` | ← chevron | — | + circle button |
| NavBarTitle | `NavBarTitle` | — | title | — |
| NavBarClose | `NavBarClose` | — | — | ✕ circle button |
| NavBarActionTitleAction | `NavBarActionTitleAction` | text action | title | blue text action |
| NavBarBackTitleAction | `NavBarBackTitleAction` | ← chevron | title | blue text action |
| NavBarBackAction | `NavBarBackAction` | ← chevron | — | blue text action |

### Layout specs
- Height: 64 dp, horizontal padding: 20 dp
- Leading/trailing icon buttons: 34 dp circle (1.5 dp border) via `Template`
- Info icon (bare, no border): 22 dp, blue tint
- Title: 225 dp wide, absolutely centred in the bar
- Text actions: `MyTheme.CaptionMedium` (13sp medium); trailing text = `dashBlue`, leading text = `textPrimary`

### Examples

```kotlin
// Back only
NavBarBack(onBackClick = { findNavController().popBackStack() })

// Back + title
NavBarBackTitle(
    title = stringResource(R.string.masternode_keys_title),
    onBackClick = { findNavController().popBackStack() }
)

// Back + title + info icon
NavBarBackTitleInfo(
    title = stringResource(R.string.owner_keys_title),
    onBackClick = { findNavController().popBackStack() },
    onInfoClick = { showInfoDialog() }
)

// Back + title + plus button
NavBarBackTitlePlus(
    title = stringResource(R.string.owner_keys_title),
    onBackClick = { findNavController().popBackStack() },
    onPlusClick = { viewModel.addKey() }
)

// Title + close button
NavBarTitleClose(
    title = stringResource(R.string.confirm_title),
    onCloseClick = { dialog.dismiss() }
)

// Text action + title + blue text action
NavBarActionTitleAction(
    title = stringResource(R.string.filter_title),
    leadingActionText = stringResource(R.string.cancel),
    onLeadingActionClick = { dismiss() },
    trailingActionText = stringResource(R.string.apply),
    onTrailingActionClick = { applyFilters() }
)
```

### TopNavBase (base function — use only when no named variant fits)

```kotlin
TopNavBase(
    leadingIcon = ImageVector.vectorResource(R.drawable.ic_menu_chevron),
    onLeadingClick = onBackClick,
    trailingIcon = Icons.Default.Add,
    onTrailingClick = onAddClick,
    centralPart = false          // hide title area
)
```

Key parameters: `leadingIcon`, `leadingText`, `onLeadingClick`, `trailingIcon`, `trailingIconCircle` (false = bare icon, no border), `trailingText`, `onTrailingClick`, `centralPart`, `title`.

---

## Button Mapping (btn -> DashButton)
When Figma designs specify button styles, map them to DashButton as follows:

### Button Sizes
- `btn-l` -> `DashButton(size = Size.Large)` - 48dp height, 16sp text
- `btn-m` -> `DashButton(size = Size.Medium)` - 42dp height, 14sp text
- `btn-s` -> `DashButton(size = Size.Small)` - 36dp height, 13sp text
- `btn-xs` -> `DashButton(size = Size.ExtraSmall)` - 28dp height, 12sp text

### Button Styles
- `filled-blue` -> `DashButton(style = Style.FilledBlue)` - Blue background, white text
- `filled-orange` -> `DashButton(style = Style.FilledOrange)` - Orange background, white text
- `filled-red` -> `DashButton(style = Style.FilledRed)` - Red background, white text
- `tinted-gray` -> `DashButton(style = Style.TintedGray)` - Light gray background, dark text
- `tinted-blue` -> `DashButton(style = Style.TintedBlue)` - Light blue background, blue text
- `plain-blue` -> `DashButton(style = Style.PlainBlue)` - Transparent background, blue text
- `plain-black` -> `DashButton(style = Style.PlainBlack)` - Transparent background, black text
- `stroke-gray` -> `DashButton(style = Style.StrokeGray)` - Gray border, transparent background

### Example
```kotlin
// Figma: btn-l filled-blue
DashButton(
    text = stringResource(R.string.continue_text),
    style = Style.FilledBlue,
    size = Size.Large,
    onClick = { /* action */ }
)

// Figma: btn-l tinted-gray
DashButton(
    text = stringResource(R.string.cancel),
    style = Style.TintedGray,
    size = Size.Large,
    onClick = { /* action */ }
)
```

## ListItem variants (Figma: List1–List11, ListEmptyState)

There are two layers:

1. **Numbered variants `ListItem1` … `ListItem11`** — strongly-typed wrappers, one per Figma `ListX` symbol in the updated **List** playground (Figma node `7968:2076`). Prefer these when a row matches a design symbol exactly. They live in:
   ```
   common/src/main/java/org/dash/wallet/common/ui/components/ListItemVariants.kt
   ```
2. **General-purpose `ListItem`** — a single flexible composable for ad-hoc combinations not covered by a numbered symbol. `ListEmptyState` handles the empty-list placeholder. Both live in:
   ```
   common/src/main/java/org/dash/wallet/common/ui/components/ListItem.kt
   ```

All variants share the same row scaffold (14 dp horizontal / 12 dp vertical padding, 20 dp gap, vertically centred) and are transparent — wrap one or more in `Menu` for the standard rounded white card.

### Numbered variant quick-reference (node `7968:2076`)

| Variant | Shape | Signature |
|---|---|---|
| `ListItem1` | label \| value | `(label, value, trailing = null)` — optional `trailing` slot after the value |
| `ListItem2` | label \| multi-line value | `(label, valueLines)` |
| `ListItem3` | label \| icon + value | `(label, value, leadingIcon = ic_dash_blue_filled)` |
| `ListItem4` | title \| gray value › | `(label, value)` |
| `ListItem5` | action › | `(action)` |
| `ListItem6` | title / help \| value › | `(title, helpText, value)` |
| `ListItem7` | help / value \| copy icon | `(helpText, value, trailingIcon = ic_copy, onTrailingIconClick)` |
| `ListItem8` | label \| amount + Dash symbol | `(label, amount, amountIcon = ic_dash_d_black)` |
| `ListItem9` | version block \| status block | `(title, subtitle1, subtitle2, trailingTitle, trailingHelpText, trailingHelpIcon = ic_left_right_arrows)` |
| `ListItem10` | secondary text / primary text | `(secondaryText, primaryText, primaryColor = null)` — colour the value, e.g. a blue link |
| `ListItem11` | label / primary text | `(label, primaryText, primaryMaxLines = ∞)` — cap + ellipsise the value |

Every variant also takes `modifier` and an optional `onClick`. Example:

```kotlin
Menu {
    ListItem1(label = "Network", value = "Mainnet")
    ListItem4(label = "Backup wallet", value = "Recommended", onClick = { /* navigate */ })
    ListItem5(action = "Recover from seed", onClick = { /* navigate */ })
}
```

### General-purpose `ListItem`

**Figma section node ID:** `2760:14713`

### Layout structure

```
[topLabel                                    ]
Row { [leadingContent]  [left]  [trailing]   }
[bottomLabel                                 ]
```

### Parameters

| Parameter | Type | Description |
|---|---|---|
| `topLabel` | `String?` | Full-width gray label above the row (List12/18 style) |
| `bottomLabel` | `String?` | Full-width gray label below the row |
| `leadingContent` | `@Composable (() -> Unit)?` | Icon/thumbnail prepended to the row (Merchant/ATM style) |
| `label` | `String?` | Tertiary gray "key" text — left side of **key-value** rows |
| `showInfoIcon` | `Boolean` | ℹ icon after `label` or `title` (List10) |
| `helpTextAbove` | `String?` | Small gray text above `title` (List13/14/22) |
| `title` | `String?` | Primary value text (LabelLarge) — **content-block** mode |
| `titleColor` | `Color?` | Override colour for `title` (default text/primary; e.g. blue for a link — List10) |
| `subtitle` | `String?` | Small gray text below `title` |
| `bottomHelpText` | `String?` | Small gray text at the bottom of the left column (List13) |
| `trailingText` | `String?` | Primary value text on the right |
| `trailingTextLines` | `List<String>?` | Multiple lines of value text (List6) |
| `trailingHelpText` | `String?` | Secondary text below the trailing value |
| `trailingHelpIcon` | `@DrawableRes Int?` | Small icon before `trailingHelpText` (List16) |
| `trailingActionText` | `String?` | Blue action link below the value (List5) |
| `trailingLabel` | `String?` | Small outlined chip badge (List7) |
| `trailingLeadingIcon` | `@Composable (RowScope.() -> Unit)?` | Icon **before** trailing text (List2/15/17) |
| `trailingTrailingIcon` | `@Composable (RowScope.() -> Unit)?` | Icon **after** trailing text (List3/4/20) |
| `trailingContent` | `@Composable (() -> Unit)?` | Fully custom right-side slot (List18, ATM Buy/Sell) |
| `onClick` | `(() -> Unit)?` | Row click handler |

### Left-side modes (mutually exclusive)

**Key-value mode** — set `label`:
- `label` renders as tertiary gray text at its natural width
- A `Spacer(weight=1f)` automatically pushes trailing content to the end

**Content-block mode** — set `title` (and optionally surrounding texts):
- The column expands to fill available width (`weight=1f`)
- Stack order: `helpTextAbove` (BodySmall/text-secondary) → `title` (Typography.LabelLarge, `titleColor` ?: text-primary) → `subtitle` (BodySmall/gray) → `bottomHelpText` (BodySmall/gray)
- The `helpTextAbove` + `title` pair is the Figma **List10** stacked block (secondary label over primary value); set `titleColor` for a coloured value such as a blue link.

### Variant quick-reference

| Figma variant | Parameters to use |
|---|---|
| List1, List11 | `label`, `trailingText` |
| List2, List15 | `label`, `trailingLeadingIcon { }`, `trailingText` |
| List3 | `label`, `trailingText`, `trailingTrailingIcon { }` |
| List4 | `label`, `trailingTrailingIcon { }` |
| List5 | `label`, `trailingText`, `trailingActionText` |
| List6 | `label`, `trailingTextLines` |
| List7 | `label`, `trailingLabel` |
| List8, List9 | `title` only |
| List10 | `helpTextAbove` (secondary label), `title` (primary value), optional `titleColor` for a blue link |
| List12 | `topLabel`, `bottomLabel`, `leadingContent { }`, `title`, `subtitle`, `trailingText` |
| List13 | `helpTextAbove`, `title`, `subtitle`, `bottomHelpText`, `trailingTrailingIcon { }` |
| List14, List22 | `helpTextAbove`, `title` |
| List16 | `title`, `subtitle`, `trailingText`, `trailingHelpText`, `trailingHelpIcon` |
| List17 | `label`, `trailingLeadingIcon { }`, `trailingText`, `trailingHelpText` |
| List18 | `topLabel`, `bottomLabel`, `leadingContent { }`, `title`, `subtitle`, `trailingContent { }` |
| List20 | `title`, `subtitle`, `trailingText`, `trailingTrailingIcon { }` |
| List23 | `title`, `subtitle` |
| MerchantListPrev | `leadingContent { }`, `title`, `subtitle`, `trailingText`, `trailingTrailingIcon { }` |
| ATMListPrev | `leadingContent { }`, `title`, `subtitle`, `trailingContent { BuySell() }` |

### Examples

```kotlin
// List1 — key-value
ListItem(label = "Fee", trailingText = "0.001 DASH")

// List2 — key-value with leading checkbox
ListItem(
    label = "Network",
    trailingText = "Mainnet",
    trailingLeadingIcon = { CheckboxIcon(checked = true) }
)

// List5 — key-value with blue action link
ListItem(
    label = "Address",
    trailingText = "XabCD…1234",
    trailingActionText = "Copy"
)

// List6 — key-value with multi-line value
ListItem(
    label = "Notes",
    trailingTextLines = listOf("Line 1", "Line 2", "Line 3")
)

// List7 — key-value with chip badge
ListItem(label = "Status", trailingLabel = "Active")

// List8 — standalone title
ListItem(title = "Section header")

// List10 — stacked secondary label / primary value (optionally a blue link)
ListItem(helpTextAbove = "Firebase installation ID", title = "fxUBdkvxQhO-ICxXXXN5mAI")
ListItem(
    helpTextAbove = "This is an open sourced app forked from Bitcoin Wallet",
    title = "https://github.com/dashevo/dash-wallet",
    titleColor = MyTheme.Colors.dashBlue,
    onClick = { /* open link */ }
)

// List13 — full multi-line left block with trailing icon
ListItem(
    helpTextAbove = "Registered on",
    title = "XAbcDeFgHi1234…",
    subtitle = "Valid until 2025-12-31",
    bottomHelpText = "Tap to view details",
    trailingTrailingIcon = {
        Icon(
            painter = painterResource(R.drawable.ic_dash_blue_filled),
            contentDescription = null,
            tint = LocalDashColors.current.dashBlue,
            modifier = Modifier.size(32.dp)
        )
    }
)

// List12 — wrapper labels + leading checkbox + trailing value
ListItem(
    topLabel = "Voting keys",
    bottomLabel = "Tap to select",
    leadingContent = { CheckboxIcon(checked = false) },
    title = "Key #1",
    subtitle = "Not used",
    trailingText = "0 used"
)

// List16 — two-line content on both sides
ListItem(
    title = "Operator key",
    subtitle = "Active",
    trailingText = "XpubABCD…",
    trailingHelpText = "last used today",
    trailingHelpIcon = R.drawable.ic_swap_blue
)

// Merchant-style — leading image + trailing price + arrow
ListItem(
    leadingContent = {
        AsyncImage(
            model = merchant.logoUrl,
            contentDescription = null,
            modifier = Modifier.size(40.dp).clip(CircleShape)
        )
    },
    title = merchant.name,
    subtitle = merchant.address,
    trailingText = "~2%",
    trailingTrailingIcon = {
        Icon(
            painter = painterResource(R.drawable.ic_menu_row_arrow),
            contentDescription = null,
            tint = LocalDashColors.current.textTertiary,
            modifier = Modifier.size(16.dp)
        )
    }
)

// ATM-style — custom Buy/Sell trailing buttons
ListItem(
    leadingContent = {
        Image(
            painter = painterResource(R.drawable.ic_atm),
            contentDescription = null,
            modifier = Modifier.size(40.dp)
        )
    },
    title = "Coinme ATM",
    subtitle = "0.3 mi away",
    trailingContent = {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DashButton(text = "Buy", style = Style.TintedBlue,
                size = Size.Small, stretch = false, onClick = { })
            DashButton(text = "Sell", style = Style.TintedGray,
                size = Size.Small, stretch = false, onClick = { })
        }
    }
)
```

### ListEmptyState

Displays a centred icon, heading, optional body text, and optional action row when a list has no items.

```kotlin
ListEmptyState(
    icon = {
        Icon(
            painter = painterResource(R.drawable.ic_dash_blue_filled),
            contentDescription = null,
            tint = LocalDashColors.current.dashBlue,
            modifier = Modifier.size(48.dp)
        )
    },
    heading = stringResource(R.string.no_masternode_keys),
    body = stringResource(R.string.no_masternode_keys_description),
    actions = {
        DashButton(
            text = stringResource(R.string.add_key),
            style = Style.PlainBlue,
            size = Size.Small,
            stretch = false,
            onClick = onAddKeyClick
        )
    }
)
```

### Wrapping with Menu

`ListItem` is transparent — it does not add its own card background. Wrap one or more items in `Menu` for the standard rounded white card:

```kotlin
Menu {
    ListItem(label = "Owner",    trailingText = "XpubAB…")
    ListItem(label = "Voting",   trailingText = "XpubCD…")
    ListItem(label = "Operator", trailingText = "XpubEF…")
}
```

## Feature Components (feature.top.text, feature.list, feature.single.item)

Feature components are used to display lists of features, benefits, or steps in onboarding flows, upgrade dialogs, and informational screens.

### FeatureTopText (Figma: feature.top.text)

A header component that displays a centered heading with optional text description and button.

**Figma Node ID**: 4075:36448

```kotlin
FeatureTopText(
    heading = "Security Upgrade",
    text = "Your wallet security will be upgraded to a more secure encryption system",
    showText = true,
    showButton = false
)

// With optional button
FeatureTopText(
    heading = "New Feature",
    text = "Learn more about this new feature",
    showText = true,
    showButton = true,
    buttonLabel = "Learn More",
    buttonLeadingIcon = ImageVector.vectorResource(R.drawable.ic_info),
    onButtonClick = { /* action */ }
)
```

**Parameters**:
- `heading`: String (required) - Main heading in HeadlineSmallBold style
- `text`: String? - Optional descriptive text in BodyMedium style
- `showText`: Boolean (default: true) - Controls text visibility
- `showButton`: Boolean (default: false) - Controls button visibility
- `buttonLabel`: String? - Button text
- `buttonLeadingIcon`: ImageVector? - Optional icon before button text
- `buttonTrailingIcon`: ImageVector? - Optional icon after button text
- `onButtonClick`: (() -> Unit)? - Button click handler

### FeatureList (Figma: feature.list)

A vertical list container that displays multiple feature items with consistent spacing.

**Figma Node ID**: 4075:36433

```kotlin
FeatureList(
    items = listOf(
        FeatureItem(
            heading = "Enhanced Security",
            text = "Your wallet will use the latest encryption technology",
            icon = ImageVector.vectorResource(R.drawable.ic_security)
        ),
        FeatureItem(
            heading = "Biometric Support",
            text = "Unlock your wallet with fingerprint or face recognition",
            icon = ImageVector.vectorResource(R.drawable.ic_biometric)
        )
    )
)
```

### FeatureSingleItem (Figma: feature.single.item)

An individual feature item with icon/number and text content.

**Figma Node ID**: 4075:36400

```kotlin
// With custom icon
FeatureSingleItem(
    heading = "Secure PIN",
    text = "Create a 6-digit PIN to protect your wallet",
    icon = ImageVector.vectorResource(R.drawable.ic_lock)
)

// With numbered step (Figma node: 2905:40402)
FeatureSingleItem(
    heading = "Create a secure PIN",
    text = "Choose a 6-digit PIN that you'll use to unlock your wallet",
    number = "1"
)

// Default (bordered box)
FeatureSingleItem(
    heading = "Feature Title",
    text = "Feature description"
)
```

**Parameters**:
- `heading`: String (required) - Feature title in TitleSmallMedium style
- `text`: String (required) - Feature description in BodyMedium style
- `icon`: ImageVector? - Custom icon (20dp, gray tint)
- `number`: String? - Numbered badge (blue circle with white text)

**Priority**: If both `number` and `icon` are provided, `number` takes precedence.

### FeatureItem Data Class

```kotlin
data class FeatureItem(
    val heading: String,
    val text: String,
    val icon: ImageVector? = null,
    val number: String? = null
)
```

### FeatureItemNumber (Internal Component)

A blue circular badge with white number text, used for numbered lists.

**Figma Node ID**: 2905:40402 (Background component)

```kotlin
// Used internally by FeatureSingleItem when number is provided
FeatureItemNumber(number = "1")
```

**Visual Specs**:
- Size: 20dp circle
- Background: `colors.dashBlue` (via `LocalDashColors.current`)
- Border radius: 8dp
- Text: 12sp, white, centered

### Complete Example

```kotlin
@Composable
fun SecurityUpgradeDialog() {
    Column(
        modifier = Modifier.padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(24.dp)
    ) {
        // Header section
        FeatureTopText(
            heading = "Security Upgrade",
            text = "Your wallet will be upgraded with the following security enhancements",
            showText = true,
            showButton = false
        )

        // Features list
        FeatureList(
            items = listOf(
                FeatureItem(
                    heading = "Modern Encryption",
                    text = "Latest AES-256 encryption for maximum security",
                    number = "1"
                ),
                FeatureItem(
                    heading = "Biometric Authentication",
                    text = "Use fingerprint or face recognition",
                    number = "2"
                ),
                FeatureItem(
                    heading = "Enhanced PIN Protection",
                    text = "Stronger PIN validation and recovery options",
                    number = "3"
                )
            )
        )

        // Action buttons
        DashButton(
            text = "Upgrade Now",
            style = Style.FilledBlue,
            size = Size.Large,
            onClick = { /* action */ }
        )
    }
}
```

## SheetButtonGroup (Figma: Sheet/Buttons group)

A button group component for bottom sheets and dialogs that supports 1-2 buttons in vertical or horizontal layouts. This component provides consistent button spacing, sizing, and positioning for sheet actions.

**Figma Node ID**: 4983-1849

### Basic Usage

```kotlin
// Single button (most common)
SheetButtonGroup(
    primaryButton = SheetButton(
        text = stringResource(R.string.continue_button),
        style = Style.FilledBlue,
        onClick = { /* action */ }
    )
)

// Two buttons - vertical layout
SheetButtonGroup(
    primaryButton = SheetButton(
        text = stringResource(R.string.continue_button),
        style = Style.FilledBlue,
        onClick = { /* primary action */ }
    ),
    secondaryButton = SheetButton(
        text = stringResource(R.string.cancel),
        style = Style.StrokeGray,
        onClick = { /* secondary action */ }
    ),
    orientation = ButtonGroupOrientation.Vertical
)

// Two buttons - horizontal layout
SheetButtonGroup(
    primaryButton = SheetButton(
        text = stringResource(R.string.confirm),
        style = Style.FilledBlue,
        onClick = { /* primary action */ }
    ),
    secondaryButton = SheetButton(
        text = stringResource(R.string.cancel),
        style = Style.StrokeGray,
        onClick = { /* secondary action */ }
    ),
    orientation = ButtonGroupOrientation.Horizontal
)
```

### SheetButton Data Class

```kotlin
data class SheetButton(
    val text: String,                    // Button text
    val style: Style,                    // Button style (FilledBlue, StrokeGray, etc.)
    val leadingIcon: ImageVector? = null, // Optional icon before text
    val trailingIcon: ImageVector? = null, // Optional icon after text
    val isEnabled: Boolean = true,        // Enable/disable state
    val isLoading: Boolean = false,       // Loading state with spinner
    val onClick: () -> Unit               // Click handler
)
```

### Layout Behavior

**Vertical Layout** (default):
- Primary button appears first (top)
- Secondary button appears below
- 10dp spacing between buttons
- Each button takes full width

**Horizontal Layout**:
- Secondary button appears on left
- Primary button appears on right
- 10dp spacing between buttons
- Buttons share width equally (50/50)

### Parameters

- `primaryButton`: SheetButton (required) - The main action button
- `secondaryButton`: SheetButton? (optional) - Secondary/cancel button
- `orientation`: ButtonGroupOrientation (default: Vertical) - Layout direction
- `modifier`: Modifier - Container modifier
- `horizontalPadding`: Dp (default: 40.dp) - Left/right padding
- `verticalPadding`: Dp

[... middle of the body omitted for length ...]

ns three logical layers, each with a clear responsibility:

```
@AndroidEntryPoint
class FeatureDetailsDialog : ComposeBottomSheet() {   // Layer 1: lifecycle + plumbing
    override fun Content() { FeatureDetailsContent(...) } // bridges to layer 2
}

@Composable
private fun FeatureDetailsContent(viewModel, callbacks)   // Layer 2: state collection
                                                          // collectAsState, LaunchedEffect, side effects

@Composable
internal fun FeatureDetailsView(uiState, callbacks)       // Layer 3: pure UI (preview-friendly)
```

**Layer 1 — `ComposeBottomSheet` subclass:** owns the ViewModel, reads arguments, manages window/sheet behaviour, exposes Fragment-only callbacks. Overrides `Content()` to bridge into the composable layer.

**Layer 2 — `*Content` composable (private):** receives the ViewModel, calls `collectAsState`, runs `LaunchedEffect` side effects, then delegates UI to layer 3. Holds **no** UI of its own.

**Layer 3 — `*View` composable (internal):** pure UI. Takes a `UIState` data class plus stateless lambda callbacks. Drives all `@Preview` functions.

## Example

```kotlin
@AndroidEntryPoint
class GiftCardDetailsDialog : ComposeBottomSheet() {
    override val backgroundStyle = R.style.PrimaryBackground
    override val forceExpand = true
    companion object {
        private const val ARG_TRANSACTION_ID = "transactionId"
        private const val ARG_CARD_INDEX = "cardIndex"
        private const val WAIT_LIMIT_FOR_ERROR = 60

        fun newInstance(transactionId: Sha256Hash, cardIndex: Int = 0) =
            GiftCardDetailsDialog().apply {
                arguments = bundleOf(
                    ARG_TRANSACTION_ID to transactionId,
                    ARG_CARD_INDEX to cardIndex
                )
            }
    }

    // Dialog-scoped Hilt ViewModel (lives and dies with this dialog instance)
    private val viewModel by viewModels<GiftCardDetailsViewModel>()
    // Activity-scoped ViewModel for cross-screen state (use `by activityViewModels()` if needed)
    private val ctxSpendViewModel by activityViewModels<DashSpendViewModel>()

    private var originalBrightness: Float = -1f

    private val bottomSheetCallback = object : BottomSheetBehavior.BottomSheetCallback() {
        override fun onStateChanged(bottomSheet: View, newState: Int) {}
        override fun onSlide(bottomSheet: View, slideOffset: Float) {
            if (slideOffset < -0.5) setMaxBrightness(false)
        }
    }

    // registerForActivityResult MUST be a property of the Fragment — cannot live in a composable
    private val launcher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { /* handle result */ }

    @Composable
    override fun Content() {
        GiftCardDetailsContent(
            viewModel = viewModel,
            waitLimitForError = WAIT_LIMIT_FOR_ERROR,
            onMaxBrightness = { enable -> setMaxBrightness(enable) },
            onViewTransaction = {
                deepLinkNavigate(DeepLinkDestination.Transaction(viewModel.transactionId.toString()))
            },
            onContactSupport = { contactSupport() },
            onErrorLogged = { error, msg -> ctxSpendViewModel.logError(error, msg) }
        )
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        // Read Bundle args and forward to the ViewModel exactly once
        (requireArguments().getSerializable(ARG_TRANSACTION_ID) as? Sha256Hash)?.let { txId ->
            val cardIndex = requireArguments().getInt(ARG_CARD_INDEX, 0)
            viewModel.init(txId, cardIndex)
        }
        subscribeToBottomSheetCallback()
    }

    private fun setMaxBrightness(enable: Boolean) {
        val window = dialog?.window ?: return
        val params = window.attributes
        if (enable) {
            if (originalBrightness < 0) originalBrightness = params.screenBrightness
            params.screenBrightness = 1.0f
        } else {
            params.screenBrightness = originalBrightness
        }
        window.attributes = params
    }

    private fun subscribeToBottomSheetCallback() {
        val sheet = (dialog as BottomSheetDialog)
            .findViewById<View>(com.google.android.material.R.id.design_bottom_sheet)
        sheet?.let { BottomSheetBehavior.from(it).addBottomSheetCallback(bottomSheetCallback) }
    }

    override fun dismiss() {
        setMaxBrightness(false)
        super.dismiss()
    }

    override fun onDestroyView() {
        val sheet = dialog?.findViewById<View>(com.google.android.material.R.id.design_bottom_sheet)
        sheet?.let { BottomSheetBehavior.from(it).removeBottomSheetCallback(bottomSheetCallback) }
        setMaxBrightness(false)
        super.onDestroyView()
    }
}

// ─── Layer 2: state-collection bridge ────────────────────────────────────────
@Composable
private fun GiftCardDetailsContent(
    viewModel: GiftCardDetailsViewModel,
    waitLimitForError: Int,
    onMaxBrightness: (Boolean) -> Unit,
    onViewTransaction: () -> Unit,
    onContactSupport: () -> Unit,
    onErrorLogged: (Exception, String) -> Unit
) {
    val uiState by viewModel.uiState.collectAsState()
    val context = LocalContext.current
    val activity = remember(context) { context.findFragmentActivity() }

    LaunchedEffect(uiState.error, uiState.queries) {
        if (uiState.error != null && uiState.queries == waitLimitForError) {
            onErrorLogged(uiState.error!!, "delivery failed after retries")
        }
    }

    GiftCardDetailsView(
        uiState = uiState,
        waitLimitForError = waitLimitForError,
        onMaxBrightness = onMaxBrightness,
        onViewTransaction = onViewTransaction,
        onContactSupport = onContactSupport,
        onHowToUse = { viewModel.logEvent(AnalyticsConstants.DashSpend.HOW_TO_USE) },
        onBalanceCheck = { url -> context.startActivity(Intent(Intent.ACTION_VIEW, url.toUri())) },
        onCopyNumber = { number -> number.copy(activity, "card number") },
        onCopyPin = { pin -> pin.copy(activity, "card pin") }
    )
}

// ─── Layer 3: pure UI (used by previews) ─────────────────────────────────────
@Composable
internal fun GiftCardDetailsView(
    uiState: GiftCardUIState,
    waitLimitForError: Int = 60,
    onMaxBrightness: (Boolean) -> Unit = {},
    onViewTransaction: () -> Unit = {},
    onContactSupport: () -> Unit = {},
    onHowToUse: () -> Unit = {},
    onBalanceCheck: (String) -> Unit = {},
    onCopyNumber: (String) -> Unit = {},
    onCopyPin: (String) -> Unit = {}
) {
    Column(modifier = Modifier.fillMaxWidth().padding(top = 60.dp)) {
        // … pure UI driven by uiState …
    }
}

@Preview(showBackground = true)
@Composable
private fun LoadingPreview() {
    GiftCardDetailsView(uiState = GiftCardUIState(/* loading state */))
}

@Preview(showBackground = true)
@Composable
private fun ErrorPreview() {
    GiftCardDetailsView(uiState = GiftCardUIState(/* error state */))
}
```

## Usage at call site

```kotlin
GiftCardDetailsDialog
    .newInstance(transactionId, cardIndex)
    .show(parentFragmentManager, "gift_card_details")
```

## Key rules

- **`@AndroidEntryPoint` is required** on the subclass for Hilt to inject the ViewModel obtained via `by viewModels<...>()`.
- **`newInstance(...) + bundleOf(...)`** for arguments — never pass parameters through constructors. Read in `onViewCreated` and forward to the ViewModel via an `init(...)` function exactly once.
- **ViewModel scope:**
  - `by viewModels<X>()` → scoped to the dialog (recreated per instance) — use this when state must die with the dialog.
  - `by activityViewModels<X>()` / `by exploreViewModels<X>()` (project helper) → shared with the host — use this only for cross-screen state already owned by the host.
- **Three-layer separation is mandatory.** Keep the `*Content` bridge composable **private** and **stateless apart from `collectAsState`/`LaunchedEffect`**. Keep the `*View` composable **internal** and **pure** so previews can drive it directly with `UIState` instances.
- **Side effects in layer 2, not layer 3.** All `LaunchedEffect`, `DisposableEffect`, `findFragmentActivity()`, `LocalContext` access happens in the `*Content` layer. Layer 3 receives only `uiState` and lambdas.
- **Fragment APIs stay in the subclass.** `registerForActivityResult`, `BottomSheetBehavior` callbacks, `dialog?.window` manipulation, `onDestroyView` cleanup — all live in layer 1 and are exposed to the composable via lambda parameters (e.g. `onMaxBrightness`).
- **Lifecycle cleanup is mandatory.** Anything subscribed in `onViewCreated` (sheet callbacks, brightness overrides) must be reverted in `onDestroyView` and `dismiss()`. Don't leak `BottomSheetBehavior` callbacks across recreations.
- **`forceExpand`:** set `true` for full-height detail dialogs (e.g. gift card details), `false` for short confirmation/info sheets.
- **Top padding:** the `*View` composable still needs `padding(top = 60.dp)` to clear the drag indicator and close button.
- **Previews:** drive every meaningful state (loading, success, error, empty) through layer 3 with hand-built `UIState` instances. Never preview layer 2 — it depends on a real ViewModel.
- **File placement:** `features/{module}/.../dialogs/{Feature}Dialog.kt` — all three layers in one file.

## Choosing between the two patterns

| Need | Factory function | Subclass |
|---|---|---|
| ViewModel already lives in the host (activity/parent fragment) | ✅ | — |
| One-shot async action (export, submit, retry) | ✅ | — |
| Dialog has no parameters, or only simple lambdas | ✅ | — |
| Dialog-scoped ViewModel with per-instance state | — | ✅ |
| Bundle arguments needed (survives config changes) | — | ✅ |
| `registerForActivityResult` from inside the dialog | — | ✅ |
| `BottomSheetBehavior` callbacks / window brightness control | — | ✅ |
| Long-lived polling, ticker jobs, or retry loops scoped to the dialog | — | ✅ |
