---
name: model-design
description: 通用的 UI model 設計 skill，說明如何用 Pydantic Model 驅動 JSON Schema UI 頁面與多頁流程。
---

# Model 設計 Skill（UI Model / Page 模式）

本 skill 說明如何設計 **Pydantic Model 作為 UI 頁面模型**，並透過 JSON Schema 產生與 `determine_model` 流程，
實作「多頁、多模式」的 UI；同時確保頁面辨識與 `isinstance` 判斷都安全可靠。

此 skill 是通用規則，不綁定特定 Provider 或專案。

---

## 一、核心觀念：Pydantic Model = 一個 UI 頁面

- 每一個 **UI Pydantic Model** 對應 **一個完整 UI 頁面**：
  - 該 Model 的欄位（含巢狀結構）會透過 `model_json_schema(by_alias=True)` 轉成一份 JSON Schema，
    交給前端畫出一個頁面。
  - 這裡的「頁面」可以是實體畫面，也可以是「特定模式下的配置畫面」。
- 產生 JSON Schema 的方式：
  - 一律使用 `model_json_schema(by_alias=True)`，讓欄位名稱、enum 值等都以 alias 呈現，
    成為 UI 使用的 schema。
- 任何時候，只要知道「目前是用哪個 Model 產生 schema」，就等同於知道「目前 UI 是在第幾頁、哪個模式」。

> 心智模型：**一個 UI Model = 一個可直接 render 的頁面**。

---

## 二、多頁 / 多模式：由 enum + determine_model 控制

### 1. 以 enum 作為頁面切換的入口

- 常見做法是在主 Model 中定義一個或多個 enum 欄位，用來代表「頁面」或「模式」：
  - 例：`Operation: OperationEnum = OperationEnum.Page1`
  - `OperationEnum` 可能有：`Page1`、`Page2` 等值。
- 也可以在第二層再有一個 enum 來表示子模式：
  - 例：`Mode: ModeEnum = ModeEnum.Mode1`
  - `ModeEnum` 可能有：`Mode1`、`Mode2`。

### 2. 一個實體頁面 = 一個獨立的 UI Model

當頁面或模式組合變多時，**每個組合都應該是一個獨立的 UI Model**，而不是在同一個 Model 裡用大量的 Option1l 欄位開關。例子：

- `OperationEnum`：`Page1`, `Page2`
- `ModeEnum`：`Mode1`, `Mode2`

實際 UI 頁面有三個：

- `Page1`
- `Page2_Mode1`
- `Page2_Mode2`

因此，建議建立三個對應的 Pydantic Model（略寫示意）：

```python
class OperationModel(BaseModel):
    Operation: OperationEnum = OperationEnum.Page1


class Page1(OperationModel):
    pass


class Page2_Mode1(OperationModel):
    Mode: ModeEnum = ModeEnum.Mode1


class Page2_Mode2(OperationModel):
    Mode: ModeEnum = ModeEnum.Mode2
```

> 重點：**不要用一個大 Model + 許多 Option1l 欄位，去同時覆蓋多個頁面**，而是讓「每個實際 UI 頁面」都有各自的 Model。

### 3. determine_model：由 payload 決定使用哪個 UI Model

- 系統會有一個類似 `determine_model(payload: dict)` 的函式，根據 payload 內容來決定要初始化哪個 UI Model：
  - 先從 payload 讀取 `Operation` / `Mode` 等關鍵欄位。
  - 根據組合（例如 `Operation=Page1`、`Operation=Page2+Mode=Mode1`），決定回傳 `Page1` 或 `Page2_Mode1` 等 Model 類別。
- 之後的流程（construct/build）都只針對這個 Model 做 schema 生成與驗證：
  - `/construct`：`model_json_schema(by_alias=True)` → JSON Schema → UI 頁面。
  - `/build`：接收 payload → 使用相同 Model 驗證 → alias=False 的結果作為最終資料。

---

## 三、頁面 Model 與繼承：UI 頁面間不得互相繼承

為了讓 `isinstance` 可以可靠判斷「目前是第幾頁 / 哪個模式」，**頁面與頁面之間禁止有繼承關係**。

### 1. 為什麼禁止 UI 頁面之間繼承？

- 若 `Page2` 繼承自 `OperationModel`，而 `OperationModel` 又被其他頁面共用，
  則 `isinstance(obj, OperationModel)` 會對多個頁面同時為 True，造成頁面判斷混淆。
- 更糟的情況是：`determine_model` 不小心回傳了一個較上層的基底 UI Model，
  在後續用 `isinstance` 分支時，會讓判斷結果與預期不同。

### 2. 正確做法：

- **可以** 有「非 UI 頁面的共用 BaseModel」，用來抽出多頁共用欄位：

  ```python
  class OperationModel(BaseModel):
      Operation: OperationEnum = OperationEnum.Page1


  class Page1(OperationModel):
      pass


  class Page2(OperationModel):
      Mode: ModeEnum = ModeEnum.Mode1
  ```

- 但設計上要明確界定：
  - 哪些是「只負責共用欄位」的 base model（不直接當作 UI 頁面使用）。
  - 哪些是「實際 UI 頁面」的 model（會被 determine_model 回傳、被用來產生 schema 與驗證）。
- **determine_model 不應該回傳純共用 base model**，例如只回傳 `OperationModel`：
  - 這樣會讓後續 `isinstance(obj, OperationModel)` 與 `isinstance(obj, Page2)` 的判斷變得不精確。
  - 應確保 determine_model 只回傳「具體的 UI 頁面 Model」，如 `Page1`、`Page2_Mode1` 等。

> 規則總結：**UI 頁面 Model 之間不得互相繼承；只能繼承「非 UI 頁面」的共用 Model。**

### 3. Page-level Model vs. nested object 的繼承規則

- 在實務上，可以進一步區分：
  - **Page-level Model（代表整個頁面）**：
    - 例如 `Page1Model`, `Page2Model`, `MainOperationModel` 等。
    - 這類 Model 會被 `determine_model` 直接回傳、用來產生整頁 schema 與處理 `/construct`、`/build`。
    - 建議統一繼承某個「頁面基底」類別，例如 `BaseProviderInputModel` / `OperationModel`。
  - **Nested object / 子物件 Model**：
    - 例如頁面底下的設定群組、巢狀物件（`AdvancedSettings`, `NestedGroup` 等）。
    - 這些只是頁面中的一部分，不代表一個獨立頁面，也不會被 `determine_model` 當成頁面回傳。
    - 建議只繼承一般的 `BaseModel`，**不要** 繼承頁面用的 `BaseProviderInputModel` 或其他 page-level base。

- 原因：
  - 讓「哪一些類別是頁面」在型別層級上清楚可見：
    - 看到繼承 `BaseProviderInputModel`（或專案定義的頁面 base）就知道它是 page-level Model。
    - 看到繼承 `BaseModel` 則代表只是巢狀物件，不會單獨當成頁面。
  - 避免 nested object 也帶有頁面用的通用欄位（例如 `skip`, `limit`, `daemon`），造成 schema 與 payload 結構混亂。

> 簡單說：**只有代表一整個頁面的 Model 才應該（直接或間接）繼承 `BaseProviderInputModel`；
> 頁面底下的巢狀物件一律繼承一般的 `BaseModel`。**

---

## 四、isinstance 與頁面判斷

- 一旦決定「哪些 Model 代表 UI 頁面」，就可以安心使用 `isinstance` 來判斷目前頁面：

  ```python
  def handle_construct(model: BaseModel) -> dict:
      if isinstance(model, Page1):
          # 畫面是 Page1
          ...
      elif isinstance(model, Page2_Mode1):
          # 畫面是 Page2 Mode1
          ...
  ```

- 這依賴前一節的設計：
  - 頁面 Model 之間不繼承，避免 `isinstance` 命中多個型別。
  - determine_model 永遠回傳「具體頁面 Model」，避免上層 base 被誤用為頁面。

---

## 五、所有 UI Model 必須有 default value

- 所有參與 UI 的欄位（也就是 UI Model 的欄位）**都必須定義 default value**：
  - 這些 default 就是「UI 初始狀態」，代表使用者還沒做出任何選擇時，頁面一開啟的值。
- 原因與好處：
  - construct 初次呼叫時，可以直接以 `model_dump(by_alias=True)` 的結果當作 UI 預設 payload。
  - JSON Schema 的 `default` 欄位能完整表示頁面的既定起始狀態。
  - 使多輪 `/construct` 更簡單：只要修改 payload 部分欄位，其餘欄位可由 default 自動補齊。

### 1. default value 實務要點

- enum 欄位：
  - 一律指定一個合理的預設值，例如 `OperationEnum.Page1`、`ModeEnum.Mode1`。
- bool 欄位：
  - 必須顯式給 `True`/`False`，例如 `Field(False, alias="WF7")`。
- 巢狀設定物件：
  - 若頁面一開始就顯示該設定區塊，建議使用 `default_factory` 產生內層 model 的 default：

    ```python
    class Page2(OperationModel):
        Mode: ModeEnum = ModeEnum.Mode1
        AdvancedSettings: AdvancedSettingsModel = Field(
            default_factory=AdvancedSettingsModel,
            alias="Advanced Settings",
        )
    ```

- 若某個區塊應該依開關動態顯示／隱藏，則：
  - 開關欄位本身仍要有 default（例如 `False`）。
  - construct 端可依開關移除或保留該區塊的 schema（見 construct-design skill）。

---

## 六、單一頁面內多個相依選項的處理（避免 page 數爆炸）

有些情境下，**同一個 UI 頁面內有很多互相有相依的選項**，例如：

- 同一頁面上有 4 個 checkbox：`A`, `B`, `C`, `D`。
- 每個 checkbox 控制是否要顯示對應的 detail settings 區塊：`A Settings`, `B Settings`, `C Settings`, `D Settings`。

> 若直接把「每一種 checkbox 組合」都做成一個獨立頁面 Model，4 個 checkbox 會變成 2^4 = 16 種頁面，Model 難以維護。

### 設計原則

- 這種情境下，我們仍然把它視為「**同一個頁面**」，因此：
  - **只用一個 UI Model** 來描述這一頁：
    - 例如一個 Model 裡同時有 4 個 checkbox 欄位與 4 個對應的 Settings 欄位。
  - 不為每一種 checkbox 組合（每個子集合）建立新的頁面 Model。
- 各個 checkbox 與 detail settings 的相依關係，交給 `/construct` 負責：
  - construct 讀取 payload 中 checkbox 的值。
  - 依照開關值 **動態刪除** 不需要顯示的 Settings schema 節點。

### 實作模式（範例心智模型）

- Model 結構：
  - Model 裡同時保留多個 boolean 欄位（例如 `Option1`, `Option2`, `Option3`, `Option4`），
    以及對應的 settings 巢狀欄位（例如 `Option1 Settings`, `Option2 Settings` …）。
- construct 邏輯：
  - 若 `Option1` 為 False，則在 schema 中移除 `Option1 Settings`。
  - 若 `Option2` 為 False，則移除 `Option2 Settings`，其餘依此類推。
- 如此一來：
  - UI 仍然是單一頁面（單一 UI Model）。
  - 頁面數不會因為 checkbox 的組合而指數級爆炸。
  - checkbox 與其 detail settings 的相依關係清楚地集中在 construct 邏輯中實現。

---

## 七、巢狀物件自動生成設定區塊（不需額外 json_schema_extra）

- 只要在 page-level Model 中宣告 **子 Model 型別** 的欄位（例：`feature_settings: FeatureSettings = Field(default_factory=FeatureSettings)`），
  JSON Schema 就會自動把它呈現為一個巢狀設定區塊。
- 不需要、也不建議為了「顯示/隱藏設定區塊」再加上 `json_schema_extra={"collapse": True}` 等額外屬性；
  前端已經能從 schema 結構辨識巢狀層級。
- UI 互動應透過 construct 階段決定是否保留該欄位的 schema：
  - 例：勾選 `Enable Feature` 才顯示 `Feature Settings` → construct 看到 `enable_feature=False` 時直接移除 `Feature Settings` 的 schema。

```python
class FeatureSettings(BaseModel):
    threshold: int = Field(0, alias="Threshold")


class MainPage(BaseProviderInputModel):
    enable_feature: bool = Field(False, alias="Enable Feature")
    feature_settings: FeatureSettings = Field(
        default_factory=FeatureSettings,
        alias="Feature Settings",
    )
```

- 實作重點：
  1. page-level Model 與 nested Model 依舊遵守「頁面用 base（`BaseProviderInputModel`） vs. 一般 `BaseModel`」的界線。
  2. 若需要 collapse/expand 效果，交給前端預設或 construct schema patch，不要在 model 上硬寫 UI-only metadata，避免日後調整時需改多處。

---

## 七、下拉選單預設為「未選取」的設計

有些 dropdown / select 欄位需要在 UI 初始狀態下表達「尚未選擇任何有效選項」，同時又希望：

- enum 的候選值中不出現一個實際可選擇的「空白選項」。

### 建議的 enum 與欄位設計

- 在 enum 中明確加入一個代表「未選取」的成員，值為空字串：

  ```python
  class OptionEnum(str, Enum):
      Option1 = "Option1"
      Option2 = "Option2"
      EMPTY = ""  # represents "no selection" in UI


  class DefaultPageModel(BaseModel):
      Option: OptionEnum = Field(
          OptionEnum.EMPTY,
          alias="Option",
      )
  ```

- 模型層面的效果：
  - Pydantic 的欄位 default 是 `OptionEnum.EMPTY`，表示 UI 起始狀態「尚未選擇」。
  - `model_json_schema(by_alias=True)` 產生的 schema 中：
    - `enum` 會包含 `""` 與其他有效選項字串。
    - 欄位的 `default` 也是空字串。

### 與 construct schema patcher 的配合

- 為了避免 UI 下拉選單中出現可選的「空白行」，可以在 `/construct` 階段配合
  `vcosmosactioninfo.schema_patcher.update_schema_empty_enum`：

  ```python
  from vcosmosactioninfo import schema_patcher


  schema = SomeModel.model_json_schema(by_alias=True)
  schema = schema_patcher.update_schema_empty_enum(schema)
  ```

- `update_schema_empty_enum` 會：
  - 深度走訪 schema。
  - 對每個 `"enum"` list，若包含空字串 `""`，就從該 list 中移除它。
- 如此設計的綜合效果：
  - Model 的 `default` 仍然可以是空字串，表示「尚未選擇」。
  - 前端 UI 渲染 dropdown 時只會看到有效選項，不會出現可點選的空白選項。

---

## 八、enum / UI breaking change 的向下相容設計（determine_model）

有時候 UI / Model 需要演進，導致 **enum 值或欄位型別發生 breaking change**，但後端仍需支援舊版 payload。

### 設計原則

- 建議在 `determine_model(payload: dict)` 中集中處理向下相容邏輯：
  - 收到舊版 payload 時，先「修補 payload」成為符合新版 Model 的格式，再建立 Model 實例。
  - 這樣可以讓 construct/build 其餘流程都只面對新版 Model 與 enum，不必到處寫「舊版特例」。
- 注意 alias：
  - payload 可能同時出現 alias=False key（Python 欄位名）與 alias=True key（UI alias）。
  - 在修補邏輯中，應同時檢查與更新兩種 key。

### 範例：enum 值從 "Option1" 改為 "Option 1"

舊版 enum（示意）：

```python
# legacy enum (for illustration only)
# class OptionEnumLegacy(str, Enum):
#     Option1 = "Option1"
#     Option2 = "Option2"
```

新版 enum 與 Model：

```python
class OptionEnum(str, Enum):
    Option1 = "Option 1"
    Option2 = "Option 2"


class PageModel(BaseModel):
    SelectOption: OptionEnum = Field(
        OptionEnum.Option1,
        alias="Select Option",
    )
```

在 `determine_model` 中處理舊值 → 新值的映射：

```python
def determine_model(payload: dict):  # noqa: PLR0911
    # Support both internal field name and alias
    option = payload.get("SelectOption") or payload.get("Select Option")

    # Backward compatibility: map legacy enum values to new ones
    if option == "Option1":
        payload["SelectOption"] = OptionEnum.Option1
        payload["Select Option"] = OptionEnum.Option1

    if option == "Option2":
        payload["SelectOption"] = OptionEnum.Option2
        payload["Select Option"] = OptionEnum.Option2

    return PageModel(**payload)
```

- 重點：
  - `determine_model` 先把 payload 修補成符合新版 enum 的值，再建立 `PageModel` 實例。
  - construct/build 之後看到的都會是「新世界」的 enum 值與欄位結構。
  - 同時更新 alias=False / alias=True key，避免之後序列化時出現不一致的狀態。

---

## 九、與其他 skill 的關聯

- Model 設計是 construct/build 模式的基礎：
  - `/construct` 如何 patch schema、顯示/隱藏區塊，請參考：`.github/skills/construct-design/SKILL.md`。
  - `/build` 如何驗證 payload、產出最終 alias=False 結果，請參考：`.github/skills/build-design/SKILL.md`。
- 本 skill 聚焦在：
  - 如何切分 UI Model 與頁面。
  - 如何利用 enum + determine_model 控制多頁流程。
  - 如何避免繼承造成 `isinstance` 判斷混亂。
  - 為什麼所有 UI Model 都必須有 default value。

> 若在擴充新的 UI 頁面或模式時，請先依本 skill 設計好對應的 Model 結構，再撰寫 construct/build 邏輯與測試。

---

## 十、UI widgets 範例目錄（原 UI widgets examples Skill）

以下整理常見 UI 欄位型態與 `json_schema_extra` 寫法，供建模時參考。所有屬性仍以 `spec/provider-development-guideline.md` 為準，此處僅示範寫法。

> **showHeading 規範：** 若某元件在 [spec/provider-development-guideline.md](../../../spec/provider-development-guideline.md) 的屬性表裡標示支援 `showHeading`，建模時一律設為 `True`，以統一顯示該欄位的字首標題。這實際上控制「是否顯示標題文字」，不是字體樣式調整；若未來前端要改預設顯示策略，只需更新 spec。

### 1. 基本文字輸入

- **Regular text input**

```python
regular_input: str = Field(
  "",
  alias="Regular Input Field",
  json_schema_extra={
    "placeholder": "This is a regular input field",
  },
)
```

- **Required text input**（UI hint + `/build` 驗證）

```python
required_input: str = Field(
  "",
  alias="Required Input Field",
  json_schema_extra={
    "placeholder": "This field is mandatory",
    "mandatory": True,
  },
)
```

- **Disabled text input**

```python
disabled_input: str = Field(
  "Disabled value",
  alias="Disabled Input Field",
  json_schema_extra={
    "placeholder": "This field is disabled",
    "disabled": True,
  },
)
```

- **Text area（多行）**

```python
text_area: str = Field(
  "",
  alias="Text Area",
  max_length=260,
  json_schema_extra={
    "placeholder": "This is a text area. You have to set maxLength to be greater than 250",
  },
)
```

- **Tooltip 文字欄位**

```python
tooltip_field: str = Field(
  "",
  alias="Field With Tooltip",
  json_schema_extra={
    "placeholder": "Tooltip and placeholder",
    "toolTip": "<p>Your tooltip content</p>",
  },
)
```

### 2. 選擇與切換控件

- **Integer with min/max**

```python
integer_field: int = Field(
  1,
  alias="Integer",
  json_schema_extra={
    "placeholder": "Integer only field. Max and min are optional",
    "maximum": 10,
    "minimum": 1,
  },
)
```

- **Disabled integer**

```python
disabled_integer_field: int = Field(
  5,
  alias="Disabled Integer",
  json_schema_extra={
    "placeholder": "Integer only field. Max and min are optional",
    "maximum": 10,
    "minimum": 1,
    "disabled": True,
  },
)
```

- **Number（float）**

```python
number_field: float = Field(
  1.5,
  alias="Number",
  json_schema_extra={
    "placeholder": "Number only field. Max and min are optional",
    "maximum": 10,
    "minimum": 1,
  },
)
```

- **Checkbox**

```python
checkbox_field: bool = Field(
  False,
  alias="Checkbox",
)
```

- **Radio（水平）**

```python
class RadioDemoEnum(str, Enum):
  OPTION_1 = "Option 1"
  OPTION_2 = "Option 2"


radio_field: RadioDemoEnum = Field(
  RadioDemoEnum.OPTION_1,
  alias="Radio Button Group",
  json_schema_extra={
    "ui": "radio",
  },
)
```

- **Radio（垂直 + heading）**

```python
vertical_radio_field: RadioDemoEnum = Field(
  RadioDemoEnum.OPTION_1,
  alias="Vertical Radio With Heading",
  json_schema_extra={
    "ui": "radio",
    "radioDirection": "vertical",
    "showHeading": True,
  },
)
```

### 3. 進階元件

- **Multiple select**

```python
class MultiSelectEnum(str, Enum):
  OPTION1 = "option1"
  OPTION2 = "option2"
  OPTION3 = "option3"


multi_select: list[MultiSelectEnum] = Field(
  default_factory=lambda: [MultiSelectEnum.OPTION1],
  alias="Multiple Select",
  json_schema_extra={
    "placeholder": "select your choice",
  },
)
```

- **Markdown display**

```python
markdown_demo: str = Field(
  "# Title\n- item 1\n- item 2",
  alias="Markdown Demo",
  json_schema_extra={
    "ui": "markdown",
    "showHeading": True,
  },
)
```

- **Duration picker（秒）**

```python
duration_picker: int = Field(
  1500,
  alias="Duration Picker",
  json_schema_extra={
    "ui": "durationPicker",
    "customizedText": "Range 1500 secs",
    "maximum": 10,
    "minimum": 1,
    "showHeading": True,
  },
)
```

- **Duration picker（分鐘 baseUnit）**

```python
duration_picker_with_base_unit: int = Field(
  60,
  alias="Duration Picker (Minutes)",
  json_schema_extra={
    "ui": "durationPicker",
    "customizedText": "Range 1500 secs",
    "maximum": 120,
    "minimum": 60,
    "baseUnit": "minute",
    "showHeading": True,
  },
)
```

- **Nested child objects（設定區塊）**

```python
class ChildSettings(BaseModel):
  threshold: int = Field(0, alias="Threshold")


class ParentModel(BaseModel):
  enable_feature: bool = Field(False, alias="Enable Feature")
  feature_settings: ChildSettings = Field(
    default_factory=ChildSettings,
    alias="Feature Settings",
  )
```

巢狀欄位自動渲染為獨立設定區塊；`json_schema_extra` 只需描述欄位 UI hint，不必再加 collapse metadata。

---

### 4. Resource browser / viewer（檔案資源選擇與預覽）

Resource 相關欄位的型別與選項定義在 `vcosmosactioninfo._resource_model` 中，常見組合為：

- `ResourceModel`：代表一筆資源（含 `id`, `settings`, `metaData`）。
- `ResourceUIEnum.RESOURCE_BROWSE`：上傳 / 選擇資源的 UI。
- `ResourceUIEnum.RESOURCE_VIEWER`：純顯示用的 viewer UI（不由使用者輸入）。
- `ResourceOptsBrowse`：resourceBrowse 的參數設定。
- `ResourceOptsViewer`：resourceViewer 的參數設定。

#### 4.1 Resource browser（上傳/選擇資源欄位）

基本 pattern：

```python
from vcosmosactioninfo._resource_model import (
    ResourceModel,
    ResourceOptsBrowse,
    ResourceOptsModeEnum,
    ResourceOptsTypeEnum,
    ResourceUIEnum,
)


user_upload_exe: list[ResourceModel] = Field(
    [],
    alias="Upload EXE",
    json_schema_extra={
        "resourceOpts": ResourceOptsBrowse(
            mode=ResourceOptsModeEnum.SINGLE,
            type=ResourceOptsTypeEnum.BINARY,
            extensions=["exe"],
        ).model_dump(),
        "ui": ResourceUIEnum.RESOURCE_BROWSE,
        "showHeading": True,
    },
)
```

Resource browser 的幾個重要設定：

- 接受單筆或多筆 resource：
  - `mode=ResourceOptsModeEnum.SINGLE`：僅允許選擇一筆資源。
  - `mode=ResourceOptsModeEnum.MULTIPLE`：允許選擇多筆資源。
- 資源類型：
  - `type=ResourceOptsTypeEnum.BINARY`：檔案類型。
  - `type=ResourceOptsTypeEnum.STRING`：文字。
  - `type=ResourceOptsTypeEnum.SECRET`：機敏字串（例如 API key）。
  - `type=ResourceOptsTypeEnum.ALL`：不限類型。
- 檔案副檔名（僅對 `BINARY` 有意義）：
  - `extensions=["zip"]`：只允許特定副檔名。
  - 建議使用空的 `extensions=[]` 代表接受所有副檔名（比「省略 extensions」更明確，便於閱讀與維護）。

#### 4.2 Resource viewer（對應的預覽欄位）

資源 viewer 欄位是「純顯示用」，使用者不會在 payload 裡主動輸入它；其 default 會在 `/construct` 端透過 patcher 自動從對應的 resourceBrowse 欄位複製。

設計建議：

- viewer 欄位的 **欄位名稱（key）本身不重要**，UI 不會直接顯示這個 JSON key。
- 但 **alias 需要遵守 `{dependency alias} Viewer` 規則**，以便一眼看出依附關係：
  - 例：上傳欄位 alias 是 `"Upload EXE"`，對應的 viewer alias 建議為 `"Upload EXE Viewer"`。

範例（配合上面的 `user_upload_exe`）：

```python
viewer1: list = Field(
    [],
    alias="Upload EXE Viewer",
)
```

- viewer 欄位的型別可以是 `list`（不必標 ResourceModel 型別），default 一般為 `[]`；
  真正的 default 值會在 `/construct` 階段由 patcher 覆寫成「這次 request 回傳的資源列表」。
- 若一個頁面有多個 resource browser 欄位（例如 `Upload EXE` / `Upload BIN`），可以設計多個 viewer 欄位，alias 依序為 `"Upload EXE Viewer"`、`"Upload BIN Viewer"` 等。

> 實作細節：construct 階段會使用 `schema_patcher.add_resource_viewers(schema)`，
> 自動針對 `ui == resourceBrowse` 的欄位產生同名 `*_viewer` property，並將 default 從 browser 欄位複製到 viewer，
> 相關行為說明請見 `.github/skills/construct-design/SKILL.md`。

---
