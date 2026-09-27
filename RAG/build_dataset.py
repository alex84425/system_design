"""
產生調酒 RAG 語料與評估集。

執行：python build_dataset.py
輸出：data/cocktails.jsonl  (語料，每行一杯)
      eval/eval_set.jsonl   (評估集，每行一題)

設計重點
--------
1. `text` 欄位才是要被 embedding 的內容，裡面刻意放了 metadata 沒有的資訊
   （風味、典故、手法眉角、常見錯誤）。否則這就退化成 SQL 查詢問題，不是 RAG。
2. 語料刻意塞入數個 hard negative 叢集 —— 結構近乎相同、只換基酒的配方。
   純向量檢索在這些叢集上會失效，是示範 metadata filter 與 rerank 的舞台。
3. 評估集分四種題型：factual / multi_hop / colloquial / negative。
   negative 題的答案不在語料裡，用來測系統會不會硬掰。
"""

import json
import os
from collections import Counter

# ---------------------------------------------------------------- 語料
# method: shake / stir / build / blend / throw
# strength: strong(純酒精,無軟性飲料) / medium / light(長飲)

COCKTAILS = [
    # ===== 叢集 A：Sour 三兄弟（核心 hard negative）=====
    dict(
        id="daiquiri", name_zh="黛綺莉", name_en="Daiquiri",
        base="蘭姆酒", family="Sour", method="shake", glass="淺碟香檳杯",
        strength="strong", iba="Unforgettables",
        ingredients=["白蘭姆酒 45ml", "新鮮萊姆汁 25ml", "糖漿 15ml"],
        garnish="無，或萊姆片",
        flavors=["酸", "清爽", "果香"],
        text=(
            "黛綺莉是蘭姆酒 Sour 的原型，只有蘭姆酒、萊姆汁、糖漿三樣，"
            "卻是檢驗調酒師基本功的標準題——因為沒有任何東西可以躲。"
            "1900 年前後誕生於古巴東部的同名礦區，據說是美國工程師 Jennings Cox "
            "手邊只剩這三樣材料時的即興之作。"
            "口感乾淨俐落，酸度銳利但被糖漿收住，喝起來比實際酒精度輕盈許多。"
            "關鍵在於萊姆必須現榨，市售瓶裝萊姆汁的苦味會毀掉整杯。"
            "搖盪要快而短，過久會過度稀釋，讓酒體變得水感。"
            "海明威特別偏好的版本會加入葡萄柚汁與瑪拉斯奇諾櫻桃利口酒、並省略糖漿，"
            "稱為 Hemingway Daiquiri 或 Papa Doble。"
        ),
    ),
    dict(
        id="margarita", name_zh="瑪格麗特", name_en="Margarita",
        base="龍舌蘭", family="Sour", method="shake", glass="瑪格麗特杯或淺碟杯",
        strength="strong", iba="Unforgettables",
        ingredients=["龍舌蘭 35ml", "君度橙酒 20ml", "新鮮萊姆汁 15ml"],
        garnish="半圈鹽口",
        flavors=["酸", "果香", "鹹"],
        text=(
            "瑪格麗特的結構與黛綺莉完全相同——基酒、柑橘、甜味——只是把蘭姆酒換成龍舌蘭，"
            "糖漿換成橙酒。這個替換讓它從清爽轉為帶著植物性與土壤氣息。"
            "鹽口是它的簽名，但只抹半圈是專業做法，讓客人可以自行選擇要不要沾到鹽。"
            "抹鹽時用萊姆片沾濕杯緣外側再滾鹽，鹽不該掉進酒裡。"
            "基酒建議用 100% 龍舌蘭製的 Blanco，混釀的 mixto 會帶來廉價的甜膩感。"
            "冷凍沙冰版本（Frozen Margarita）是 1970 年代美國餐廳發明的變體，"
            "與搖盪版本在口感上幾乎是兩種不同的酒。"
        ),
    ),
    dict(
        id="sidecar", name_zh="側車", name_en="Sidecar",
        base="白蘭地", family="Sour", method="shake", glass="淺碟杯",
        strength="strong", iba="Unforgettables",
        ingredients=["干邑白蘭地 50ml", "君度橙酒 20ml", "新鮮檸檬汁 20ml"],
        garnish="無，或糖口",
        flavors=["酸", "果香", "溫潤"],
        text=(
            "側車是 Sour 家族中最優雅的一支，把瑪格麗特的龍舌蘭換成干邑、萊姆換成檸檬，"
            "骨架依舊，氣質卻完全不同——干邑的橡木桶陳年讓酒體變得圓潤而有層次。"
            "名字來自一戰後巴黎，一位常搭摩托車邊車來酒吧的美軍軍官。"
            "倫敦派做法是干邑、橙酒、檸檬各三分之一等比；法國派則拉高干邑比例，"
            "上面的配方偏向後者，酒感更明確。"
            "糖口是可選的，加了會讓它更接近甜點。用 VSOP 等級以上的干邑差異相當明顯。"
        ),
    ),

    # ===== 叢集 B：琴酒 Sour =====
    dict(
        id="white-lady", name_zh="白色佳人", name_en="White Lady",
        base="琴酒", family="Sour", method="shake", glass="淺碟杯",
        strength="strong", iba="Unforgettables",
        ingredients=["琴酒 40ml", "君度橙酒 30ml", "新鮮檸檬汁 20ml"],
        garnish="檸檬皮油",
        flavors=["酸", "花香", "乾"],
        text=(
            "白色佳人可以視為側車的琴酒版本——同樣是基酒、橙酒、檸檬的三角結構。"
            "由 Harry MacElhone 在 1920 年代的巴黎 Harry's New York Bar 定型。"
            "琴酒的杜松子與橙酒的柑橘皮香氣在杯中疊合，收尾乾淨偏乾。"
            "加入少量蛋白會讓口感變得絲滑並產生細緻泡沫，是常見的現代改良，"
            "但傳統版本不含蛋白。橙酒比例偏高是這杯的特徵，不要照 Sour 標準砍低。"
        ),
    ),
    dict(
        id="aviation", name_zh="飛行", name_en="Aviation",
        base="琴酒", family="Sour", method="shake", glass="淺碟杯",
        strength="strong", iba="Contemporary Classics",
        ingredients=["琴酒 45ml", "瑪拉斯奇諾櫻桃利口酒 15ml", "紫羅蘭利口酒 5ml", "新鮮檸檬汁 15ml"],
        garnish="瑪拉斯奇諾櫻桃",
        flavors=["酸", "花香", "果香"],
        text=(
            "飛行因為紫羅蘭利口酒而呈現淡淡的天空藍紫色，名字也由此而來。"
            "1916 年出現在 Hugo Ensslin 的調酒書中，但紫羅蘭利口酒在二戰後幾乎絕跡，"
            "導致中間數十年的食譜都省略它，只剩琴酒、櫻桃利口酒、檸檬。"
            "2007 年 Rothman & Winter 復刻紫羅蘭利口酒後，完整版本才重新流行。"
            "紫羅蘭利口酒非常霸道，超過 5ml 整杯會變成肥皂味，這是新手最常犯的錯。"
            "瑪拉斯奇諾指的是無色的櫻桃核蒸餾利口酒，不是罐頭裡那種紅色糖漬櫻桃。"
        ),
    ),
    dict(
        id="last-word", name_zh="最後一語", name_en="Last Word",
        base="琴酒", family="Sour", method="shake", glass="淺碟杯",
        strength="strong", iba="New Era",
        ingredients=["琴酒 22.5ml", "綠夏翠絲 22.5ml", "瑪拉斯奇諾櫻桃利口酒 22.5ml", "新鮮萊姆汁 22.5ml"],
        garnish="無",
        flavors=["酸", "草本", "甜"],
        text=(
            "最後一語是等比四材料的典範，四樣各佔四分之一，記憶成本極低卻難以複製。"
            "禁酒令前誕生於底特律運動俱樂部，沉寂半世紀後由西雅圖調酒師 Murray Stenson "
            "在 2004 年重新挖出，成為精釀調酒復興的代表作。"
            "綠夏翠絲是這杯的靈魂——由法國修道院以 130 種草本製成，配方至今保密，"
            "酒精度高達 55%，草本的辛香會主導整杯的中段。"
            "等比不代表可以隨便量，四樣的比例只要偏掉一點平衡就會塌。"
            "把琴酒換成波本就是 Final Ward，換成梅斯卡爾則是 Mezcal Last Word。"
        ),
    ),
    dict(
        id="corpse-reviver-2", name_zh="亡者復甦二號", name_en="Corpse Reviver No. 2",
        base="琴酒", family="Sour", method="shake", glass="淺碟杯",
        strength="strong", iba="New Era",
        ingredients=["琴酒 22.5ml", "君度橙酒 22.5ml", "麗葉白酒 22.5ml", "新鮮檸檬汁 22.5ml", "艾碧斯潤杯"],
        garnish="橙皮油",
        flavors=["酸", "草本", "乾"],
        text=(
            "又一杯等比四材料，但多了艾碧斯潤杯這道工序——在冰鎮好的杯子裡倒入少量艾碧斯，"
            "轉一圈讓內壁掛上薄薄一層，再把多餘的倒掉。茴香香氣只出現在鼻尖，不干擾入口。"
            "屬於 Corpse Reviver 系列，顧名思義是解宿醉用的晨間酒。"
            "Harry Craddock 在 1930 年的 Savoy Cocktail Book 中留下警語："
            "連喝四杯，這些東西會讓屍體再死一次。"
            "麗葉白酒（Lillet Blanc）現行配方比戰前甜，有些酒吧改用 Cocchi Americano "
            "來還原原本較苦的版本。"
        ),
    ),
    dict(
        id="bees-knees", name_zh="蜂之膝", name_en="Bee's Knees",
        base="琴酒", family="Sour", method="shake", glass="淺碟杯",
        strength="strong", iba="無",
        ingredients=["琴酒 60ml", "新鮮檸檬汁 22.5ml", "蜂蜜糖漿 22.5ml"],
        garnish="檸檬皮",
        flavors=["酸", "甜", "花香"],
        text=(
            "禁酒令時期的產物，用蜂蜜與檸檬掩蓋私釀琴酒的粗劣氣味，名字是當年的俚語，"
            "意思是「最棒的東西」。"
            "蜂蜜不能直接下——冷的酒液會讓它結塊沉底，必須先用蜂蜜與熱水以 3:1 調成蜂蜜糖漿。"
            "這是新手最常踩的雷，也是它跟一般糖漿 Sour 在製程上唯一的差別。"
            "換成不同蜜源會明顯改變風味：龍眼蜜厚重、洋槐蜜清淡、百花蜜居中。"
            "把琴酒換成威士忌、檸檬換成一部分薑汁，就接近 Penicillin 的思路。"
        ),
    ),
    dict(
        id="clover-club", name_zh="三葉草俱樂部", name_en="Clover Club",
        base="琴酒", family="Sour", method="shake", glass="淺碟杯",
        strength="strong", iba="Contemporary Classics",
        ingredients=["琴酒 45ml", "新鮮檸檬汁 15ml", "覆盆子糖漿 15ml", "蛋白 1 顆份"],
        garnish="覆盆子",
        flavors=["酸", "果香", "綿密"],
        text=(
            "粉紅色、頂著一層厚實泡沫，來自 1900 年代費城 Bellevue-Stratford 飯店的同名男士俱樂部。"
            "蛋白不提供味道，只負責質地——它把酸味的稜角包起來，讓口感變得絲絨般綿密。"
            "作法上必須先乾搖（不加冰搖 15 秒讓蛋白起泡），再加冰濕搖降溫，"
            "順序顛倒會做不出穩定的泡沫層。這個雙段搖盪是所有含蛋白調酒的通則。"
            "覆盆子糖漿建議自製，市售的通常過甜且帶人工香精味。"
        ),
    ),
    dict(
        id="gimlet", name_zh="琴蕾", name_en="Gimlet",
        base="琴酒", family="Sour", method="shake", glass="淺碟杯",
        strength="strong", iba="Contemporary Classics",
        ingredients=["琴酒 45ml", "萊姆糖漿 15ml"],
        garnish="萊姆片",
        flavors=["酸", "清爽", "乾"],
        text=(
            "琴蕾只有兩樣材料，卻是調酒史上爭議最多的一杯——正統派堅持必須用 Rose's "
            "萊姆糖漿，現代派則改用現榨萊姆汁加糖漿。兩者風味差距極大，"
            "前者帶著獨特的煮過的萊姆皮味，後者清亮許多。"
            "起源說法是英國皇家海軍用萊姆汁預防壞血病，摻琴酒讓水手願意喝下去。"
            "錢德勒在《漫長的告別》裡寫下「真正的琴蕾是一半琴酒一半 Rose's 萊姆汁，"
            "別的什麼都不加」，讓這杯酒帶上了文學光環。"
        ),
    ),
    dict(
        id="southside", name_zh="南方", name_en="Southside",
        base="琴酒", family="Sour", method="shake", glass="淺碟杯",
        strength="strong", iba="無",
        ingredients=["琴酒 60ml", "新鮮萊姆汁 22.5ml", "糖漿 22.5ml", "薄荷葉 6-8 片"],
        garnish="薄荷葉",
        flavors=["酸", "薄荷", "清爽"],
        text=(
            "可以理解成不加蘇打水、改用琴酒的莫希托，或是加了薄荷的琴酒版黛綺莉。"
            "傳說與芝加哥南區的黑幫有關，但更可信的來源是紐約長島的 Southside 鄉村俱樂部。"
            "薄荷要用拍打的方式喚醒香氣，不要搗爛——葉脈破裂會釋出葉綠素的苦澀。"
            "這是新手處理薄荷時最常犯的錯，莫希托也適用同樣原則。"
            "搖完務必雙重過濾，避免碎葉浮在表面影響口感。"
        ),
    ),

    # ===== 叢集 C：苦甜三角（Negroni 家族，強 hard negative）=====
    dict(
        id="negroni", name_zh="內格羅尼", name_en="Negroni",
        base="琴酒", family="Bitter", method="stir", glass="古典杯",
        strength="strong", iba="Unforgettables",
        ingredients=["琴酒 30ml", "金巴利 30ml", "甜香艾酒 30ml"],
        garnish="橙片或橙皮",
        flavors=["苦", "甜", "草本"],
        text=(
            "三等份的琴酒、金巴利、甜香艾酒，是入門苦味調酒的標準起點。"
            "1919 年佛羅倫斯，Camillo Negroni 伯爵要求把美式基調（Americano）裡的蘇打水"
            "換成琴酒，於是誕生了這杯。"
            "加冰攪拌而非搖盪——沒有果汁或蛋白的酒都該用攪拌，搖盪會產生不必要的氣泡與碎冰，"
            "破壞酒體的厚度與清澈度。這是 stir 與 shake 的判斷通則。"
            "橙皮要在杯口上方擠壓噴出皮油再放入，香氣差別非常明顯。"
            "覺得太苦可以把金巴利減至 20ml，或換成苦度較低的 Aperol。"
        ),
    ),
    dict(
        id="boulevardier", name_zh="花花公子", name_en="Boulevardier",
        base="波本威士忌", family="Bitter", method="stir", glass="古典杯",
        strength="strong", iba="無",
        ingredients=["波本威士忌 30ml", "金巴利 30ml", "甜香艾酒 30ml"],
        garnish="橙皮",
        flavors=["苦", "甜", "溫潤"],
        text=(
            "把內格羅尼的琴酒換成波本，就是花花公子。結構完全相同，"
            "但威士忌的焦糖與香草讓苦味變得柔和圓潤，秋冬更適合。"
            "1927 年出現在 Harry MacElhone 的書中，名字來自當時一本巴黎的僑民雜誌。"
            "許多酒吧會把威士忌比例拉高到 45ml，讓基酒不被金巴利壓過去——"
            "因為波本的風味強度不如琴酒的杜松子那樣能站住腳。"
            "這杯與內格羅尼、Old Pal 三者的文字描述極為接近，是檢索系統的經典陷阱。"
        ),
    ),
    dict(
        id="old-pal", name_zh="老朋友", name_en="Old Pal",
        base="裸麥威士忌", family="Bitter", method="stir", glass="淺碟杯",
        strength="strong", iba="無",
        ingredients=["裸麥威士忌 30ml", "金巴利 30ml", "不甜香艾酒 30ml"],
        garnish="檸檬皮",
        flavors=["苦", "乾", "辛香"],
        text=(
            "與花花公子只差一個字：甜香艾酒換成不甜香艾酒。"
            "這一個替換讓整杯從圓潤變得乾瘦銳利，苦味更直接，幾乎沒有甜味緩衝。"
            "裸麥的辛香與胡椒感在這個乾燥的架構裡被放大，是三者中最硬派的一杯。"
            "同樣出自 MacElhone，據說是為一位常客調的。"
            "內格羅尼、花花公子、老朋友三杯並列，是解釋「為什麼需要 metadata 過濾」"
            "最好的教材——光靠語意相似度，檢索系統分不出這三杯。"
        ),
    ),
    dict(
        id="americano", name_zh="美式基調", name_en="Americano",
        base="金巴利", family="Bitter", method="build", glass="高球杯",
        strength="light", iba="Unforgettables",
        ingredients=["金巴利 30ml", "甜香艾酒 30ml", "蘇打水適量"],
        garnish="橙片",
        flavors=["苦", "氣泡", "清爽"],
        text=(
            "內格羅尼的前身，也是它的低酒精版本——把琴酒換成蘇打水即可。"
            "1860 年代米蘭的 Caffè Campari 首創，原名 Milano-Torino，"
            "因為金巴利來自米蘭、香艾酒來自杜林。後來因美國觀光客特別愛點而改名。"
            "007 系列小說裡，龐德喝的第一杯酒就是美式基調。"
            "直接在杯中建構，不需要搖盪或攪拌，是入門苦味酒最溫和的選擇，"
            "酒精度大約只有內格羅尼的三分之一。"
        ),
    ),

    # ===== 叢集 D：Martini 家族 =====
    dict(
        id="dry-martini", name_zh="不甜馬丁尼", name_en="Dry Martini",
        base="琴酒", family="Martini", method="stir", glass="馬丁尼杯",
        strength="strong", iba="Unforgettables",
        ingredients=["琴酒 60ml", "不甜香艾酒 10ml"],
        garnish="橄欖或檸檬皮",
        flavors=["乾", "草本", "冰冽"],
        text=(
            "調酒界的聖杯，也是最難做好的一杯，因為它無處可藏。"
            "琴酒與不甜香艾酒的比例從 2:1 一路演化到現在常見的 6:1 甚至更乾。"
            "邱吉爾據說只要看一眼香艾酒的瓶子就夠了。"
            "必須攪拌不能搖盪——搖盪會讓琴酒產生細碎氣泡並過度稀釋，"
            "失去馬丁尼標誌性的油潤稠密口感。龐德的 shaken, not stirred 在專業上是異端。"
            "橄欖與檸檬皮是兩種不同的酒：橄欖帶來鹹味與圓潤，檸檬皮則強化乾爽與柑橘頂香。"
            "所有材料與杯子都必須預先冰鎮到接近零度。"
        ),
    ),
    dict(
        id="gibson", name_zh="吉普森", name_en="Gibson",
        base="琴酒", family="Martini", method="stir", glass="馬丁尼杯",
        strength="strong", iba="無",
        ingredients=["琴酒 60ml", "不甜香艾酒 10ml"],
        garnish="醃漬珍珠洋蔥",
        flavors=["乾", "鹹", "草本"],
        text=(
            "配方與不甜馬丁尼完全相同，唯一的差別是裝飾物：橄欖換成醃漬珍珠洋蔥。"
            "但這個小小的替換改變的不只是外觀——洋蔥的醃漬液會滲入酒中，"
            "帶來一絲酸鹹與蔬菜氣息，讓整杯的收尾比馬丁尼更鮮明。"
            "名字來源說法多達五、六種，最流行的是插畫家 Charles Dana Gibson 的版本。"
            "這杯與不甜馬丁尼是整份語料裡材料最接近的一組——材料欄位一模一樣，"
            "差異只存在於裝飾與描述文字中，任何只看材料的檢索都會失敗。"
        ),
    ),
    dict(
        id="martinez", name_zh="馬丁尼茲", name_en="Martinez",
        base="琴酒", family="Martini", method="stir", glass="淺碟杯",
        strength="strong", iba="無",
        ingredients=["老湯姆琴酒 45ml", "甜香艾酒 45ml", "瑪拉斯奇諾櫻桃利口酒 5ml", "柑橘苦精 2 dash"],
        garnish="檸檬皮",
        flavors=["甜", "草本", "圓潤"],
        text=(
            "被認為是馬丁尼的祖先，比例卻幾乎相反——香艾酒的份量與琴酒相當，"
            "而且用的是甜香艾酒，因此整杯偏甜、偏厚，與現代不甜馬丁尼是兩個世界。"
            "老湯姆琴酒（Old Tom）是介於荷蘭式與倫敦乾式之間的甜型琴酒，"
            "用倫敦乾琴酒替代會讓這杯失去原本的柔軟度。"
            "從馬丁尼茲到馬丁尼的演變，大致就是一部十九世紀末調酒口味逐漸變乾的歷史。"
        ),
    ),
    dict(
        id="hanky-panky", name_zh="靈犀一點", name_en="Hanky Panky",
        base="琴酒", family="Martini", method="stir", glass="淺碟杯",
        strength="strong", iba="無",
        ingredients=["琴酒 45ml", "甜香艾酒 45ml", "芬味樹苦酒 7.5ml"],
        garnish="橙皮",
        flavors=["苦", "草本", "薄荷"],
        text=(
            "由倫敦 Savoy 飯店的傳奇女調酒師 Ada Coleman 創作，是少數明確出自女性之手的經典。"
            "她為演員 Charles Hawtrey 調製，對方喝完說了句 By Jove, that is the real hanky-panky，"
            "酒名就此定下。"
            "關鍵在於芬味樹（Fernet-Branca）只用 7.5ml——這款義大利苦酒帶著強烈的薄荷與"
            "藥草味，多一點就會徹底蓋過琴酒。少量時它反而扮演放大器，讓香艾酒的甜變得立體。"
        ),
    ),

    # ===== 叢集 E：Manhattan 家族 =====
    dict(
        id="manhattan", name_zh="曼哈頓", name_en="Manhattan",
        base="裸麥威士忌", family="Manhattan", method="stir", glass="淺碟杯",
        strength="strong", iba="Unforgettables",
        ingredients=["裸麥威士忌 50ml", "甜香艾酒 20ml", "安格式苦精 2 dash"],
        garnish="酒漬櫻桃",
        flavors=["甜", "辛香", "溫潤"],
        text=(
            "與馬丁尼並列為攪拌類調酒的兩大支柱，誕生於 1870 年代的紐約曼哈頓俱樂部。"
            "裸麥威士忌的胡椒辛香與甜香艾酒的葡萄甜味互相拉扯，苦精則把兩端縫合起來。"
            "用波本會讓整杯變甜變圓，是另一種風格但失去裸麥特有的骨架。"
            "櫻桃必須用 Luxardo 這類酒漬櫻桃，罐頭的螢光紅櫻桃會把這杯拉低一個檔次。"
            "香艾酒開瓶後必須冷藏並在一個月內用完，氧化的香艾酒是曼哈頓走味的頭號元兇。"
            "把甜香艾酒換成不甜就是 Dry Manhattan，各半則是 Perfect Manhattan。"
        ),
    ),
    dict(
        id="rob-roy", name_zh="羅伯羅伊", name_en="Rob Roy",
        base="蘇格蘭威士忌", family="Manhattan", method="stir", glass="淺碟杯",
        strength="strong", iba="無",
        ingredients=["蘇格蘭調和威士忌 50ml", "甜香艾酒 20ml", "安格式苦精 2 dash"],
        garnish="酒漬櫻桃",
        flavors=["甜", "煙燻", "溫潤"],
        text=(
            "曼哈頓的蘇格蘭版本，配方逐項對應，只換基酒。"
            "1894 年紐約 Waldorf 飯店為一齣同名歌劇首演所創，主角是蘇格蘭民族英雄 Rob Roy。"
            "蘇格蘭威士忌的麥芽甜與淡淡泥煤讓整杯比曼哈頓更沉、更帶煙燻感。"
            "用艾雷島的重泥煤威士忌會過於霸道，調和式或斯佩賽單一麥芽是較穩的選擇。"
            "曼哈頓與羅伯羅伊是又一組只換基酒的 hard negative，"
            "使用者問「有沒有威士忌加香艾酒的調酒」時，兩杯都會被撈出來。"
        ),
    ),
    dict(
        id="vieux-carre", name_zh="老廣場", name_en="Vieux Carré",
        base="裸麥威士忌", family="Manhattan", method="stir", glass="古典杯",
        strength="strong", iba="無",
        ingredients=["裸麥威士忌 30ml", "干邑白蘭地 30ml", "甜香艾酒 30ml",
                     "班尼狄克丁香甜酒 1 tsp", "佩喬苦精 2 dash", "安格式苦精 2 dash"],
        garnish="檸檬皮",
        flavors=["甜", "草本", "複雜"],
        text=(
            "1938 年誕生於紐奧良法國區的 Hotel Monteleone 旋轉酒吧，名字就是法國區的舊稱。"
            "罕見地同時使用兩種基酒——裸麥的辛辣與干邑的果香各佔一半，"
            "再加上班尼狄克丁的蜂蜜草本，層次比曼哈頓複雜得多。"
            "兩款苦精缺一不可：佩喬（Peychaud's）帶茴香與櫻桃，安格式偏丁香與肉桂，"
            "少了任何一種平衡都會傾斜。"
            "班尼狄克丁只用一茶匙，它的甜度很高，過量會讓整杯變成糖水。"
        ),
    ),

    # ===== 叢集 F：威士忌經典 =====
    dict(
        id="old-fashioned", name_zh="古典雞尾酒", name_en="Old Fashioned",
        base="波本威士忌", family="Old Fashioned", method="build", glass="古典杯",
        strength="strong", iba="Unforgettables",
        ingredients=["波本或裸麥威士忌 45ml", "方糖 1 顆", "安格式苦精 2 dash", "水少許"],
        garnish="橙皮",
        flavors=["甜", "辛香", "溫潤"],
        text=(
            "調酒這個詞最原始的定義：烈酒、糖、水、苦精四樣東西的組合。"
            "十九世紀中期，當新式調酒越出越花俏時，老派客人會說「給我來杯老派做法的」，"
            "酒名就是這樣來的。"
            "做法是先把方糖用苦精浸濕、加一點水搗散，再分次加入威士忌與冰塊逐步攪拌稀釋。"
            "分次加冰是關鍵，一次倒滿會稀釋不均。"
            "整顆大冰球能減緩融化速度，讓最後幾口不會變成水。"
            "不要放水果丁下去搗——那是美國禁酒令後的墮落版本，會讓酒變成果醬水。"
        ),
    ),
    dict(
        id="sazerac", name_zh="薩澤拉克", name_en="Sazerac",
        base="裸麥威士忌", family="Old Fashioned", method="stir", glass="古典杯",
        strength="strong", iba="New Era",
        ingredients=["裸麥威士忌 50ml", "方糖 1 顆", "佩喬苦精 3 dash", "艾碧斯潤杯"],
        garnish="檸檬皮油（皮不放入）",
        flavors=["辛香", "茴香", "乾"],
        text=(
            "紐奧良的市定官方雞尾酒，也是美國最古老的調酒之一，可追溯到 1850 年代。"
            "原本以干邑為基酒，十九世紀末法國葡萄根瘤蚜災害導致干邑短缺，才改用裸麥威士忌。"
            "艾碧斯潤杯後必須把多餘的倒掉，只留內壁那層薄膜。"
            "與古典雞尾酒最大的差異在於：檸檬皮擠出油後不放進杯裡，"
            "香氣只停留在表面，這是薩澤拉克的規矩。"
            "佩喬苦精不可用安格式替代，兩者風味走向完全不同。"
        ),
    ),
    dict(
        id="whiskey-sour", name_zh="威士忌酸酒", name_en="Whiskey Sour",
        base="波本威士忌", family="Sour", method="shake", glass="古典杯或淺碟杯",
        strength="strong", iba="Contemporary Classics",
        ingredients=["波本威士忌 45ml", "新鮮檸檬汁 30ml", "糖漿 15ml", "蛋白（可選）"],
        garnish="檸檬片與櫻桃",
        flavors=["酸", "甜", "溫潤"],
        text=(
            "Sour 家族裡知名度最高的一支，也是最早被寫進調酒書的其中之一，"
            "1862 年 Jerry Thomas 的 Bartender's Guide 已經收錄。"
            "波本的香草與焦糖讓酸味不至於太尖銳，是初次接觸烈酒調酒的常見入門選擇。"
            "加蛋白的版本稱為 Boston Sour，口感綿密許多；"
            "淋上一層紅酒的則是 New York Sour，紅酒會浮在表面形成漸層。"
            "2:1:1 的酒、酸、甜比例是所有 Sour 的通用起點，記住這個就能推導出大半個家族。"
        ),
    ),
    dict(
        id="penicillin", name_zh="盤尼西林", name_en="Penicillin",
        base="蘇格蘭威士忌", family="Sour", method="shake", glass="古典杯",
        strength="strong", iba="無",
        ingredients=["調和蘇格蘭威士忌 60ml", "新鮮檸檬汁 22.5ml", "蜂蜜薑汁糖漿 22.5ml",
                     "艾雷島單一麥芽 7.5ml（漂浮）"],
        garnish="糖漬薑片",
        flavors=["酸", "辛香", "煙燻"],
        text=(
            "2005 年由紐約 Milk & Honey 的澳洲調酒師 Sam Ross 創作，"
            "是二十一世紀最成功的新經典之一，名字來自它像感冒糖漿的療癒感。"
            "結構是威士忌版的蜂之膝，但多了薑的辛辣與最後那 7.5ml 的泥煤漂浮。"
            "漂浮的艾雷島威士忌不能攪進去——它要停在表面，讓煙燻味先進鼻腔，"
            "入口才是蜂蜜與薑。這個嗅覺與味覺分層是整杯的設計核心。"
            "蜂蜜薑汁糖漿用等量蜂蜜與熱水，加入拍碎的新鮮薑塊浸泡後過濾。"
        ),
    ),
    dict(
        id="paper-plane", name_zh="紙飛機", name_en="Paper Plane",
        base="波本威士忌", family="Sour", method="shake", glass="淺碟杯",
        strength="strong", iba="無",
        ingredients=["波本威士忌 22.5ml", "艾普羅 22.5ml", "諾尼諾阿瑪羅 22.5ml", "新鮮檸檬汁 22.5ml"],
        garnish="無",
        flavors=["酸", "苦", "果香"],
        text=(
            "2008 年由 Sam Ross 創作，結構上直接致敬最後一語——同樣是等比四材料，"
            "但把琴酒系換成波本、綠夏翠絲換成兩款義大利苦酒。"
            "名字來自 M.I.A. 的歌曲 Paper Planes。"
            "艾普羅提供柑橘與微苦，諾尼諾阿瑪羅帶來葡萄與焦糖的深度，"
            "兩者疊在波本上形成非常獨特的苦甜果香。"
            "諾尼諾價格不低，用其他阿瑪羅替代會明顯改變平衡，Montenegro 是較接近的選項。"
        ),
    ),
    dict(
        id="rusty-nail", name_zh="鏽釘", name_en="Rusty Nail",
        base="蘇格蘭威士忌", family="Duo", method="build", glass="古典杯",
        strength="strong", iba="無",
        ingredients=["蘇格蘭調和威士忌 45ml", "蜂蜜香甜酒 25ml"],
        garnish="檸檬皮",
        flavors=["甜", "草本", "溫潤"],
        text=(
            "只有兩樣材料，蘇格蘭威士忌加上 Drambuie 蜂蜜香甜酒，直接在杯中加冰建構。"
            "Drambuie 本身就是以蘇格蘭威士忌為基底、加入石楠花蜜與香料製成，"
            "所以這杯其實是同一種酒的兩種形態疊在一起，融合度天生就高。"
            "1960 年代因鼠黨（Rat Pack）成員愛喝而大紅。"
            "比例可依甜度偏好在 2:1 到 1:1 之間調整，冬天適合往甜的方向走。"
        ),
    ),

    # ===== 叢集 G：長飲與高球 =====
    dict(
        id="mojito", name_zh="莫希托", name_en="Mojito",
        base="蘭姆酒", family="Highball", method="build", glass="高球杯",
        strength="light", iba="Unforgettables",
        ingredients=["白蘭姆酒 45ml", "新鮮萊姆汁 30ml", "細砂糖 2 tsp", "薄荷葉 6 片", "蘇打水適量"],
        garnish="薄荷枝",
        flavors=["酸", "薄荷", "氣泡"],
        text=(
            "古巴國民調酒，源自十六世紀水手用甘蔗酒、萊姆與薄荷治療壞血病的偏方。"
            "薄荷只能輕拍或輕壓，絕不能搗爛——這是莫希托做失敗最常見的原因，"
            "搗爛的葉子會釋出苦澀的葉綠素，把清爽感全毀掉。"
            "碎冰要填滿杯子，冰量不足會讓酒迅速變溫變稀。"
            "蘇打水最後才加，加完只需輕輕提拉一下讓材料交融，過度攪拌會消掉氣泡。"
            "海明威在哈瓦那 La Bodeguita del Medio 留下的那句「我的莫希托在此」"
            "至今仍掛在牆上。"
        ),
    ),
    dict(
        id="tom-collins", name_zh="湯姆可林斯", name_en="Tom Collins",
        base="琴酒", family="Highball", method="build", glass="可林斯杯",
        strength="light", iba="Contemporary Classics",
        ingredients=["琴酒 45ml", "新鮮檸檬汁 30ml", "糖漿 15ml", "蘇打水適量"],
        garnish="檸檬片與櫻桃",
        flavors=["酸", "氣泡", "清爽"],
        text=(
            "本質上就是加了蘇打水的琴酒 Sour，在杯中直接建構。"
            "名字來自 1874 年紐約的一場惡作劇風潮——人們告訴朋友有個叫 Tom Collins 的人"
            "正在酒吧裡說他壞話，讓對方衝去找人，酒吧就順勢推出同名調酒。"
            "與琴費士的差異極為細微：湯姆可林斯用可林斯杯直接建構、加冰塊；"
            "琴費士則先搖盪再倒入較小的杯子、通常不加冰或少冰，泡沫更綿密。"
            "兩者材料幾乎相同，是又一組專門用來測試檢索精度的近似配方。"
        ),
    ),
    dict(
        id="gin-fizz", name_zh="琴費士", name_en="Gin Fizz",
        base="琴酒", family="Fizz", method="shake", glass="高球杯",
        strength="light", iba="Contemporary Classics",
        ingredients=["琴酒 45ml", "新鮮檸檬汁 30ml", "糖漿 10ml", "蘇打水適量"],
        garnish="檸檬片",
        flavors=["酸", "氣泡", "綿密"],
        text=(
            "與湯姆可林斯材料幾乎一致，差別在製程：琴費士必須先把酒、檸檬、糖漿搖盪過，"
            "再濾入杯中沖蘇打水，因此表面會有一層細緻泡沫。"
            "傳統上不加冰塊或只加少量，杯型也比可林斯杯矮小。"
            "加入蛋白的版本是 Silver Fizz，加蛋黃是 Golden Fizz，全蛋則是 Royal Fizz。"
            "紐奧良的 Ramos Gin Fizz 再加上鮮奶油與橙花水，傳說要搖盪十二分鐘，"
            "是所有費士中最費工的一杯。"
        ),
    ),
    dict(
        id="moscow-mule", name_zh="莫斯科騾子", name_en="Moscow Mule",
        base="伏特加", family="Highball", method="build", glass="銅杯",
        strength="light", iba="Contemporary Classics",
        ingredients=["伏特加 45ml", "新鮮萊姆汁 10ml", "薑汁啤酒 120ml"],
        garnish="萊姆角",
        flavors=["辛香", "氣泡", "清爽"],
        text=(
            "1941 年洛杉磯，一個賣不掉伏特加的酒商、一個賣不掉薑汁啤酒的餐廳老闆，"
            "加上一個有一堆銅杯庫存的人，三方聯手促銷的產物。"
            "這杯酒幾乎單槍匹馬把伏特加帶進了美國市場。"
            "銅杯不只是行銷噱頭——金屬導熱快，能讓杯壁迅速結霜，入口更冰冽。"
            "薑汁啤酒（ginger beer）與薑汁汽水（ginger ale）是兩種東西，"
            "前者經發酵、薑味濃烈辛辣，用後者會做出一杯乏味的酒。"
            "換成蘭姆酒是 Dark 'n' Stormy，換成龍舌蘭是 Mexican Mule。"
        ),
    ),
    dict(
        id="dark-n-stormy", name_zh="黑色風暴", name_en="Dark 'n' Stormy",
        base="蘭姆酒", family="Highball", method="build", glass="高球杯",
        strength="light", iba="Contemporary Classics",
        ingredients=["黑蘭姆酒 60ml", "薑汁啤酒 100ml", "萊姆汁 10ml"],
        garnish="萊姆角",
        flavors=["辛香", "氣泡", "焦糖"],
        text=(
            "百慕達的國民飲料，也是極少數擁有註冊商標的調酒——"
            "Gosling's 公司登記了這個名字，法律上必須使用 Gosling's Black Seal 蘭姆酒"
            "才能稱作 Dark 'n' Stormy。"
            "正確做法是先倒薑汁啤酒，再讓黑蘭姆酒沿著吧叉匙緩緩浮在上層，"
            "形成上深下淺的漸層，名字裡的暴風雨雲就是這個視覺。"
            "喝之前要不要攪拌，是百慕達人之間永恆的爭論。"
        ),
    ),
    dict(
        id="paloma", name_zh="帕洛瑪", name_en="Paloma",
        base="龍舌蘭", family="Highball", method="build", glass="高球杯",
        strength="light", iba="無",
        ingredients=["龍舌蘭 50ml", "葡萄柚汽水 100ml", "新鮮萊姆汁 15ml", "鹽少許"],
        garnish="葡萄柚片與鹽口",
        flavors=["酸", "苦", "氣泡"],
        text=(
            "在墨西哥本地，帕洛瑪比瑪格麗特更常見，是真正的國民日常飲品。"
            "葡萄柚的微苦與龍舌蘭的植物性意外地契合，加上一撮鹽能同時壓苦提甜。"
            "傳統用 Squirt 或 Jarritos 這類墨西哥葡萄柚汽水，"
            "講究一點的酒吧會改用現榨葡萄柚汁加蘇打水與糖漿自行組合，風味清亮許多。"
            "比瑪格麗特容易做得多，也更解渴，適合炎熱天氣。"
        ),
    ),
    dict(
        id="cuba-libre", name_zh="自由古巴", name_en="Cuba Libre",
        base="蘭姆酒", family="Highball", method="build", glass="高球杯",
        strength="light", iba="Unforgettables",
        ingredients=["白蘭姆酒 50ml", "可樂 120ml", "新鮮萊姆汁 10ml"],
        garnish="萊姆角",
        flavors=["甜", "氣泡", "果香"],
        text=(
            "蘭姆可樂加上萊姆，就從一杯隨便的調飲變成自由古巴——"
            "那 10ml 萊姆汁是兩者唯一的差別，卻切開了甜膩感，是不可省略的一步。"
            "名字來自 1900 年前後的古巴獨立戰爭，美軍士兵舉杯高喊 Por Cuba Libre。"
            "用玻璃瓶裝的蔗糖可樂比罐裝果糖可樂效果好，氣泡更細緻、甜味更乾淨。"
        ),
    ),

    # ===== 叢集 H：熱帶 =====
    dict(
        id="mai-tai", name_zh="邁泰", name_en="Mai Tai",
        base="蘭姆酒", family="Tiki", method="shake", glass="古典杯",
        strength="strong", iba="Unforgettables",
        ingredients=["陳年蘭姆酒 40ml", "農業蘭姆酒 20ml", "橙皮酒 15ml",
                     "杏仁糖漿 15ml", "新鮮萊姆汁 20ml"],
        garnish="薄荷枝與萊姆殼",
        flavors=["酸", "堅果", "果香"],
        text=(
            "1944 年由加州的 Trader Vic 創作，他宣稱大溪地朋友喝完說了句 Maita'i roa ae"
            "（太好了），酒名由此而來。"
            "真正的邁泰裡沒有鳳梨汁——那是後來度假村為了降低成本與討好大眾"
            "加進去的變體，也是這杯酒被誤解最深的地方。"
            "杏仁糖漿（orgeat）是靈魂，由杏仁、糖與橙花水製成，"
            "它的堅果調性把兩種蘭姆酒與柑橘連接起來。"
            "兩種蘭姆酒缺一不可：陳年的提供深度，農業蘭姆（rhum agricole）"
            "以新鮮甘蔗汁蒸餾，帶來青草般的銳利前味。"
        ),
    ),
    dict(
        id="pina-colada", name_zh="鳳梨可樂達", name_en="Piña Colada",
        base="蘭姆酒", family="Tiki", method="blend", glass="颶風杯",
        strength="medium", iba="Unforgettables",
        ingredients=["白蘭姆酒 50ml", "椰漿 30ml", "鳳梨汁 50ml"],
        garnish="鳳梨片與櫻桃",
        flavors=["甜", "奶油", "果香"],
        text=(
            "波多黎各的官方國飲，1954 年由聖胡安 Caribe Hilton 飯店的 Ramón Marrero 創作。"
            "椰漿（cream of coconut）與椰奶（coconut milk）是不同的東西，"
            "前者已加糖且質地濃稠，用錯會讓整杯變得稀薄無味。"
            "可以用果汁機加冰打成沙冰，也可以搖盪後倒在碎冰上，後者口感較清爽。"
            "鳳梨汁必須是純果汁，濃縮還原的會帶罐頭味。"
            "加入黑蘭姆酒漂浮在上層，就是常見的變體 Painkiller 的雛形。"
        ),
    ),

    # ===== 叢集 I：氣泡酒 =====
    dict(
        id="french-75", name_zh="法式 75", name_en="French 75",
        base="琴酒", family="Sparkling", method="shake", glass="笛型香檳杯",
        strength="medium", iba="Contemporary Classics",
        ingredients=["琴酒 30ml", "新鮮檸檬汁 15ml", "糖漿 7.5ml", "香檳 60ml"],
        garnish="檸檬皮",
        flavors=["酸", "氣泡", "乾"],
        text=(
            "一戰時期巴黎 Harry's New York Bar 的作品，名字取自法軍的 75 公釐野戰砲——"
            "據說喝下去的後座力與之相當。"
            "本體是一杯琴酒 Sour，只是把蘇打水換成香檳，酒精度因此高出許多，"
            "卻因為氣泡與酸度喝起來異常順口，這是它危險的地方。"
            "香檳最後加，且不可搖盪。前三樣搖好濾入冰鎮過的笛型杯，再緩緩注入香檳。"
            "把琴酒換成干邑的版本在紐奧良更為流行，兩派至今各執一詞。"
        ),
    ),
    dict(
        id="aperol-spritz", name_zh="艾普羅氣泡飲", name_en="Aperol Spritz",
        base="艾普羅", family="Sparkling", method="build", glass="大酒杯",
        strength="light", iba="New Era",
        ingredients=["普羅賽克氣泡酒 90ml", "艾普羅 60ml", "蘇打水 30ml"],
        garnish="橙片",
        flavors=["苦", "甜", "氣泡"],
        text=(
            "義大利威尼托地區的傍晚儀式，3-2-1 的比例好記到不需要量杯："
            "三份氣泡酒、兩份艾普羅、一份蘇打水。"
            "艾普羅的酒精度只有 11%，苦度也遠低於金巴利，橙皮與大黃的味道偏甜，"
            "因此整杯清爽到接近軟性飲料，是夏日午後的標準配備。"
            "必須先放冰塊再倒液體，且氣泡酒先於艾普羅，否則較重的艾普羅會沉底不易混合。"
            "把艾普羅換成金巴利就是苦味明顯加重的 Campari Spritz。"
        ),
    ),
    dict(
        id="bellini", name_zh="貝里尼", name_en="Bellini",
        base="普羅賽克", family="Sparkling", method="build", glass="笛型香檳杯",
        strength="light", iba="Contemporary Classics",
        ingredients=["普羅賽克氣泡酒 100ml", "白桃果泥 50ml"],
        garnish="無",
        flavors=["甜", "果香", "氣泡"],
        text=(
            "1948 年由威尼斯 Harry's Bar 的 Giuseppe Cipriani 創作，"
            "粉橘色澤讓他想起文藝復興畫家 Giovanni Bellini 畫中聖袍的顏色。"
            "必須使用白桃而非黃桃——白桃的香氣細緻、酸度低，黃桃會過於濃烈且顏色偏橘。"
            "果泥要新鮮現打並冰鎮，罐頭桃泥的糖漿味會壓過氣泡酒。"
            "只能輕輕攪拌，過度攪動會讓氣泡散失。"
            "把白桃換成草莓是 Rossini，換成葡萄是 Puccini，都是同一間酒吧的延伸作品。"
        ),
    ),

    # ===== 叢集 J：咖啡與奶油 =====
    dict(
        id="espresso-martini", name_zh="濃縮咖啡馬丁尼", name_en="Espresso Martini",
        base="伏特加", family="Martini", method="shake", glass="淺碟杯",
        strength="strong", iba="無",
        ingredients=["伏特加 50ml", "咖啡利口酒 20ml", "現萃濃縮咖啡 30ml", "糖漿 5ml"],
        garnish="三顆咖啡豆",
        flavors=["咖啡", "甜", "綿密"],
        text=(
            "1983 年倫敦的 Dick Bradsell 創作，據說一位模特兒走進酒吧說"
            "「給我一杯能讓我清醒、然後再讓我茫掉的東西」。"
            "名字裡有馬丁尼，但它與馬丁尼家族毫無關係，只是借用了杯型。"
            "咖啡必須是現萃的濃縮並趁熱搖盪——放涼的咖啡打不出表面那層綿密的咖啡油脂泡沫，"
            "而那層泡沫正是這杯的招牌。"
            "搖盪要用力且時間夠長，讓 crema 充分乳化。"
            "三顆咖啡豆的裝飾據說代表健康、財富與幸福。"
        ),
    ),
    dict(
        id="white-russian", name_zh="白色俄羅斯", name_en="White Russian",
        base="伏特加", family="Creamy", method="build", glass="古典杯",
        strength="medium", iba="Contemporary Classics",
        ingredients=["伏特加 50ml", "咖啡利口酒 20ml", "鮮奶油 30ml"],
        garnish="無",
        flavors=["奶油", "咖啡", "甜"],
        text=(
            "在黑色俄羅斯上面加一層鮮奶油，就成了白色俄羅斯。"
            "鮮奶油應該沿著吧叉匙緩緩浮在上層，形成清楚的分層，喝之前再由客人自行攪拌。"
            "1998 年電影《謀殺綠腳趾》讓這杯酒徹底復活——主角 The Dude 全片喝了九杯，"
            "影迷至今稱它為 Caucasian。"
            "用全脂鮮奶油而非牛奶，脂肪含量不足會無法漂浮、直接混濁下沉。"
        ),
    ),
    dict(
        id="black-russian", name_zh="黑色俄羅斯", name_en="Black Russian",
        base="伏特加", family="Duo", method="build", glass="古典杯",
        strength="strong", iba="無",
        ingredients=["伏特加 50ml", "咖啡利口酒 20ml"],
        garnish="無",
        flavors=["咖啡", "甜", "乾"],
        text=(
            "只有兩樣材料，1949 年由布魯塞爾 Hotel Metropole 的調酒師為美國駐盧森堡大使所創，"
            "名字裡的黑指的是咖啡利口酒的顏色，俄羅斯則指伏特加。"
            "加冰直接在杯中建構，比例可依甜度偏好在 5:2 到 2:1 之間調整。"
            "它與白色俄羅斯的差別只有最後那 30ml 鮮奶油，"
            "但兩杯的口感與場合完全不同——一杯是餐後甜點，一杯是烈酒。"
            "加可樂的變體叫 Dirty Black Russian。"
        ),
    ),
    dict(
        id="brandy-alexander", name_zh="白蘭地亞歷山大", name_en="Brandy Alexander",
        base="白蘭地", family="Creamy", method="shake", glass="淺碟杯",
        strength="medium", iba="Unforgettables",
        ingredients=["干邑白蘭地 30ml", "深可可香甜酒 30ml", "鮮奶油 30ml"],
        garnish="現磨肉豆蔻",
        flavors=["奶油", "巧克力", "甜"],
        text=(
            "三樣材料等比，是最經典的餐後甜點調酒之一。"
            "原始版本 Alexander 用的是琴酒，改成白蘭地後意外地更受歡迎，"
            "最終喧賓奪主成為主流。"
            "表面現磨的肉豆蔻不是裝飾——它的溫暖辛香能切開奶油的厚重感，缺了整杯會膩。"
            "必須用力搖盪讓鮮奶油充分乳化，搖不夠會油水分離。"
            "約翰藍儂曾稱它為「奶昔」，然後在 1974 年那段著名的失控期喝掉了大量這種奶昔。"
        ),
    ),

    # ===== 叢集 K：其他經典 =====
    dict(
        id="cosmopolitan", name_zh="柯夢波丹", name_en="Cosmopolitan",
        base="伏特加", family="Sour", method="shake", glass="馬丁尼杯",
        strength="strong", iba="Contemporary Classics",
        ingredients=["檸檬伏特加 40ml", "君度橙酒 15ml", "新鮮萊姆汁 15ml", "蔓越莓汁 30ml"],
        garnish="橙皮或火焰橙皮",
        flavors=["酸", "果香", "清爽"],
        text=(
            "1990 年代因《慾望城市》而成為全球現象，也因此被貼上「女性飲品」的標籤，"
            "使它在精釀調酒圈一度被不公平地看輕。"
            "結構上是一杯加了蔓越莓汁的 Kamikaze，酸度明確，並不甜膩。"
            "蔓越莓汁只佔 30ml，份量不該再多——它負責顏色與一點果酸，不是主角。"
            "用檸檬風味伏特加（citron）而非原味，是它與其他伏特加 Sour 的關鍵差異。"
            "火焰橙皮的做法是點火後擠壓皮油穿過火焰，焦糖化的柑橘香氣是專業級的收尾。"
        ),
    ),
    dict(
        id="bloody-mary", name_zh="血腥瑪麗", name_en="Bloody Mary",
        base="伏特加", family="Savory", method="throw", glass="高球杯",
        strength="medium", iba="Unforgettables",
        ingredients=["伏特加 45ml", "番茄汁 90ml", "新鮮檸檬汁 15ml",
                     "伍斯特醬 2 dash", "塔巴斯科 2 dash", "鹽與黑胡椒"],
        garnish="芹菜梗與檸檬角",
        flavors=["鹹", "辛香", "鮮味"],
        text=(
            "唯一一杯鹹味的經典調酒，也是公認的宿醉解藥。"
            "1920 年代巴黎 Harry's New York Bar 的 Fernand Petiot 所創，"
            "後來他到紐約 St. Regis 飯店任職時因名字太粗俗而改稱 Red Snapper。"
            "不能搖盪——番茄汁劇烈搖動後會起泡變稀、質地散掉。"
            "正確手法是 throw，把材料在兩個容器之間拉高互倒數次，"
            "既混合均勻又保留稠度，同時充分冰鎮。"
            "把伏特加換成琴酒就是原始的 Red Snapper，換成龍舌蘭是 Bloody Maria，"
            "換成啤酒與蛤蜊汁則是加拿大的 Caesar。"
        ),
    ),
    dict(
        id="caipirinha", name_zh="卡琵莉亞", name_en="Caipirinha",
        base="甘蔗酒", family="Sour", method="build", glass="古典杯",
        strength="strong", iba="Unforgettables",
        ingredients=["卡夏莎甘蔗酒 60ml", "萊姆 半顆切塊", "細砂糖 2 tsp"],
        garnish="無",
        flavors=["酸", "甜", "草本"],
        text=(
            "巴西國民調酒，也是少數會把整塊柑橘搗進杯裡的經典。"
            "卡夏莎（cachaça）與蘭姆酒的差別在原料：卡夏莎用新鮮甘蔗汁，"
            "多數蘭姆酒用糖蜜，因此卡夏莎帶著明顯的青草與土壤氣息。"
            "萊姆要切塊去掉中間的白色筋膜再搗，那部分是苦味來源。"
            "搗的時候用壓的、轉的，不要用力搥打表皮，過度破壞果皮同樣會出苦。"
            "用伏特加替代的版本叫 Caipiroska，用蘭姆酒的叫 Caipirissima。"
        ),
    ),
    dict(
        id="pisco-sour", name_zh="皮斯可酸酒", name_en="Pisco Sour",
        base="皮斯可", family="Sour", method="shake", glass="古典杯",
        strength="strong", iba="Contemporary Classics",
        ingredients=["皮斯可 45ml", "新鮮萊姆汁 30ml", "糖漿 20ml", "蛋白 1 顆份", "安格式苦精 3 dash"],
        garnish="苦精在泡沫上畫線",
        flavors=["酸", "花香", "綿密"],
        text=(
            "祕魯與智利爭奪所有權的國民調酒，兩國的皮斯可法規與風味也確實不同。"
            "祕魯版本禁止加水稀釋，智利版本則允許，因此祕魯皮斯可通常更濃郁。"
            "1920 年代由利馬 Morris' Bar 的美國人 Victor Morris 定型。"
            "蛋白處理同樣是先乾搖再濕搖，泡沫層要厚到足以承載表面的苦精圖案。"
            "最後那幾滴苦精不只是裝飾——聞的時候先進鼻子的是苦精的丁香肉桂，"
            "入口才是葡萄的花香，這個順序是設計過的。"
        ),
    ),
    dict(
        id="bramble", name_zh="黑莓", name_en="Bramble",
        base="琴酒", family="Sour", method="build", glass="古典杯",
        strength="strong", iba="New Era",
        ingredients=["琴酒 40ml", "新鮮檸檬汁 15ml", "糖漿 10ml", "黑莓利口酒 15ml"],
        garnish="黑莓與檸檬片",
        flavors=["酸", "果香", "甜"],
        text=(
            "1980 年代由倫敦的 Dick Bradsell 創作，他也是濃縮咖啡馬丁尼的作者。"
            "靈感來自他童年在英國鄉間採黑莓的記憶，是少數有明確在地情感的現代經典。"
            "作法是先把琴酒、檸檬、糖漿倒在碎冰上攪拌，"
            "再讓黑莓利口酒（crème de mûre）從杯緣淋下，"
            "紫紅色會沿著碎冰縫隙緩緩滲下形成大理石紋路，這個視覺是刻意設計的。"
            "碎冰不可省略，用方冰會讓漸層效果完全消失。"
        ),
    ),
    dict(
        id="jack-rose", name_zh="傑克玫瑰", name_en="Jack Rose",
        base="蘋果白蘭地", family="Sour", method="shake", glass="淺碟杯",
        strength="strong", iba="無",
        ingredients=["蘋果白蘭地 45ml", "新鮮檸檬汁 20ml", "紅石榴糖漿 15ml"],
        garnish="蘋果片",
        flavors=["酸", "果香", "甜"],
        text=(
            "禁酒令前的美國經典，基酒是 applejack 蘋果白蘭地，"
            "美國最古老的蒸餾酒之一，比波本歷史更悠久。"
            "海明威在《太陽依舊升起》裡讓主角在巴黎的飯店酒吧喝了這杯等人。"
            "紅石榴糖漿必須是真的石榴熬製，市售的多半只是紅色糖水加香精，"
            "會讓這杯變成廉價的甜飲——這是它在現代少見的主因之一。"
            "顏色應該是溫潤的玫瑰色，過於鮮豔通常代表用了人工糖漿。"
        ),
    ),
]


# ---------------------------------------------------------------- 評估集
# type: factual / multi_hop / colloquial / negative
# relevant: 正解文件 id；negative 題為空陣列

EVAL = [
    # --- factual：單跳事實 ---
    dict(id="q001", type="factual", relevant=["negroni"],
         q="Negroni 的三種材料和比例是什麼？"),
    dict(id="q002", type="factual", relevant=["daiquiri"],
         q="黛綺莉要用多少萊姆汁？"),
    dict(id="q003", type="factual", relevant=["margarita"],
         q="瑪格麗特的鹽口為什麼只抹半圈？"),
    dict(id="q004", type="factual", relevant=["aviation"],
         q="飛行為什麼是藍紫色的？"),
    dict(id="q005", type="factual", relevant=["dry-martini"],
         q="馬丁尼為什麼不能用搖的？"),
    dict(id="q006", type="factual", relevant=["gibson"],
         q="吉普森的裝飾是什麼？"),
    dict(id="q007", type="factual", relevant=["old-fashioned"],
         q="古典雞尾酒為什麼要分次加冰塊？"),
    dict(id="q008", type="factual", relevant=["mojito"],
         q="莫希托的薄荷可以搗爛嗎？"),
    dict(id="q009", type="factual", relevant=["penicillin"],
         q="盤尼西林最後漂浮的那層是什麼酒？"),
    dict(id="q010", type="factual", relevant=["espresso-martini"],
         q="濃縮咖啡馬丁尼的咖啡一定要現萃的嗎？"),
    dict(id="q011", type="factual", relevant=["bees-knees"],
         q="蜂之膝的蜂蜜為什麼不能直接加進去？"),
    dict(id="q012", type="factual", relevant=["mai-tai"],
         q="正統的邁泰裡面有鳳梨汁嗎？"),
    dict(id="q013", type="factual", relevant=["moscow-mule"],
         q="莫斯科騾子為什麼要用銅杯？"),
    dict(id="q014", type="factual", relevant=["pina-colada"],
         q="鳳梨可樂達該用椰漿還是椰奶？"),
    dict(id="q015", type="factual", relevant=["clover-club"],
         q="含蛋白的調酒為什麼要先乾搖再濕搖？"),
    dict(id="q016", type="factual", relevant=["bloody-mary"],
         q="血腥瑪麗為什麼不能用搖盪的？"),
    dict(id="q017", type="factual", relevant=["last-word"],
         q="綠夏翠絲是什麼酒？"),
    dict(id="q018", type="factual", relevant=["sazerac"],
         q="薩澤拉克的檸檬皮要放進杯子裡嗎？"),
    dict(id="q019", type="factual", relevant=["bellini"],
         q="貝里尼為什麼一定要用白桃？"),
    dict(id="q020", type="factual", relevant=["aperol-spritz"],
         q="艾普羅氣泡飲的 3-2-1 比例是指什麼？"),

    # --- hard negative 叢集：專門打檢索精度 ---
    dict(id="q021", type="factual", relevant=["boulevardier"],
         q="把 Negroni 的琴酒換成波本叫什麼？",
         note="易誤撈 negroni / old-pal，三者描述高度相似"),
    dict(id="q022", type="factual", relevant=["old-pal"],
         q="金巴利加裸麥威士忌加不甜香艾酒是哪一杯？",
         note="與 boulevardier 只差甜/不甜香艾酒"),
    dict(id="q023", type="factual", relevant=["rob-roy"],
         q="曼哈頓的蘇格蘭威士忌版本叫什麼？",
         note="易誤撈 manhattan"),
    dict(id="q024", type="factual", relevant=["gin-fizz", "tom-collins"],
         q="琴費士和湯姆可林斯差在哪裡？",
         note="兩篇都要撈到才算對"),
    dict(id="q025", type="factual", relevant=["black-russian", "white-russian"],
         q="黑色俄羅斯和白色俄羅斯的差別？",
         note="兩篇都要撈到"),
    dict(id="q026", type="factual", relevant=["dry-martini", "gibson"],
         q="馬丁尼和吉普森的材料一樣嗎？",
         note="材料欄位完全相同，差異只在文字描述"),
    dict(id="q027", type="colloquial", relevant=["daiquiri", "margarita", "sidecar"],
         q="有沒有那種酸酸甜甜、帶柑橘的短飲？",
         note="Sour 三兄弟，純向量排序近乎隨機"),

    # --- multi_hop：需跨多篇彙整 ---
    dict(id="q031", type="multi_hop", relevant=["martinez", "hanky-panky", "negroni"],
         q="我有琴酒和甜香艾酒，可以調什麼？",
         note="需跨多篇比對材料。注意不甜馬丁尼用的是不甜香艾酒，不算正解"),
    dict(id="q032", type="multi_hop", relevant=["negroni", "boulevardier", "old-pal", "americano"],
         q="有哪些調酒會用到金巴利？"),
    dict(id="q033", type="multi_hop", relevant=["last-word", "corpse-reviver-2", "paper-plane"],
         q="有哪些是四種材料等比例的調酒？"),
    dict(id="q034", type="multi_hop", relevant=["clover-club", "pisco-sour", "whiskey-sour", "white-lady"],
         q="哪些調酒會用到蛋白？"),
    dict(id="q035", type="multi_hop", relevant=["moscow-mule", "dark-n-stormy", "penicillin"],
         q="有哪些調酒是薑味的？"),
    dict(id="q036", type="multi_hop", relevant=["aviation", "last-word", "martinez"],
         q="瑪拉斯奇諾櫻桃利口酒可以拿來調什麼？"),
    dict(id="q037", type="multi_hop",
         relevant=["negroni", "boulevardier", "old-pal", "dry-martini", "gibson", "martinez",
                   "hanky-panky", "manhattan", "rob-roy", "vieux-carre", "sazerac"],
         q="哪些調酒是用攪拌而不是搖盪的？",
         note="正解等於所有 method=stir 的文件，共 11 篇。k 要開夠大才可能拿到高 Recall"),
    dict(id="q038", type="multi_hop", relevant=["mojito", "southside"],
         q="有哪些調酒會用到新鮮薄荷？"),

    # --- colloquial：口語化，與語料用詞不重疊 ---
    dict(id="q041", type="colloquial", relevant=["aperol-spritz", "americano", "bellini"],
         q="有沒有喝起來不像酒、很淡的？",
         note="語料用「低酒精」「清爽」，問題用「不像酒」，用詞零重疊"),
    dict(id="q042", type="colloquial", relevant=["brandy-alexander", "white-russian", "pina-colada"],
         q="想喝甜甜的、像甜點那種"),
    dict(id="q043", type="colloquial", relevant=["negroni", "americano", "boulevardier", "old-pal"],
         q="我喜歡苦一點的，有推薦嗎？"),
    dict(id="q044", type="colloquial", relevant=["bloody-mary"],
         q="宿醉的時候喝什麼比較好？"),
    dict(id="q045", type="colloquial", relevant=["mojito", "paloma", "tom-collins", "cuba-libre"],
         q="夏天很熱，想要清爽解渴的"),
    dict(id="q046", type="colloquial", relevant=["old-fashioned", "manhattan", "rusty-nail", "boulevardier"],
         q="冬天想喝暖一點、濃一點的"),
    dict(id="q047", type="colloquial", relevant=["dry-martini", "old-fashioned", "negroni"],
         q="第一次去酒吧不知道點什麼，有沒有安全牌？"),
    dict(id="q048", type="colloquial", relevant=["espresso-martini"],
         q="喝了會提神的調酒"),

    # --- negative：答案不在語料裡，正確行為是說不知道 ---
    dict(id="q051", type="negative", relevant=[],
         q="Negroni 的抹茶版本比例是多少？"),
    dict(id="q052", type="negative", relevant=[],
         q="長島冰茶要放幾種基酒？",
         note="語料中沒有長島冰茶"),
    dict(id="q053", type="negative", relevant=[],
         q="這些調酒的熱量各是多少大卡？"),
    dict(id="q054", type="negative", relevant=[],
         q="台北哪一間酒吧的 Negroni 最好喝？"),
    dict(id="q055", type="negative", relevant=[],
         q="孕婦可以喝哪一杯？",
         note="同時測安全性回應"),
    dict(id="q056", type="negative", relevant=[],
         q="Daiquiri 的發明人生日是哪一天？",
         note="語料提到 Jennings Cox 但沒有生日"),
    dict(id="q057", type="negative", relevant=[],
         q="琴通寧的標準配方是什麼？",
         note="語料中沒有這杯，但主題極近，最容易硬掰"),
    dict(id="q058", type="negative", relevant=[],
         q="Negroni 用哪個牌子的琴酒最好？",
         note="語料只談酒種不談品牌"),
]


# ---------------------------------------------------------------- 輸出

METHOD_ZH = {
    "shake": "搖盪 shake",
    "stir": "攪拌 stir",
    "build": "直接建構 build",
    "blend": "果汁機 blend",
    "throw": "拋接 throw",
}


def to_markdown(c):
    """一杯酒 → 一份帶 YAML frontmatter 的 markdown 文件。

    frontmatter 放結構化欄位（給 metadata filter 用），
    正文放敘述（給 embedding 用）。這是實務上最常見的語料形態，
    你的 loader 要負責把兩者拆開。
    """
    fm = [
        "---",
        f"id: {c['id']}",
        f"name_zh: {c['name_zh']}",
        f"name_en: {c['name_en']}",
        f"base: {c['base']}",
        f"family: {c['family']}",
        f"method: {c['method']}",
        f"glass: {c['glass']}",
        f"strength: {c['strength']}",
        f"iba: {c['iba']}",
        f"flavors: [{', '.join(c['flavors'])}]",
        "---",
    ]
    body = [
        "",
        f"# {c['name_zh']}　{c['name_en']}",
        "",
        f"**基酒**：{c['base']}　**手法**：{METHOD_ZH[c['method']]}　"
        f"**杯型**：{c['glass']}　**風味**：{'／'.join(c['flavors'])}",
        "",
        "## 材料",
        "",
    ]
    body += [f"- {i}" for i in c["ingredients"]]
    body += [
        "",
        f"**裝飾**：{c['garnish']}",
        "",
        "## 說明",
        "",
        c["text"],
        "",
    ]
    return "\n".join(fm + body)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    md_dir = os.path.join(here, "data", "cocktails")
    os.makedirs(md_dir, exist_ok=True)
    os.makedirs(os.path.join(here, "eval"), exist_ok=True)

    ids = [c["id"] for c in COCKTAILS]
    dupes = [k for k, v in Counter(ids).items() if v > 1]
    assert not dupes, f"重複的 id: {dupes}"

    # 1) markdown 語料：一杯一檔，這是你要餵給 loader 的東西
    for c in COCKTAILS:
        path = os.path.join(md_dir, f"{c['id']}.md")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(to_markdown(c))

    # 2) jsonl 鏡像：給評估腳本當 ground truth 對照用，不是拿來檢索的
    corpus_path = os.path.join(here, "data", "cocktails.jsonl")
    with open(corpus_path, "w", encoding="utf-8", newline="\n") as f:
        for c in COCKTAILS:
            rec = dict(c)
            rec["source"] = f"data/cocktails/{c['id']}.md"
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 3) 評估集
    known = set(ids)
    eval_path = os.path.join(here, "eval", "eval_set.jsonl")
    with open(eval_path, "w", encoding="utf-8", newline="\n") as f:
        for e in EVAL:
            bad = [r for r in e["relevant"] if r not in known]
            assert not bad, f"{e['id']} 指向不存在的文件: {bad}"
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"語料   data/cocktails/*.md   {len(COCKTAILS)} 檔")
    print(f"       data/cocktails.jsonl  （ground truth 鏡像）")
    print(f"       基酒 {dict(Counter(c['base'] for c in COCKTAILS))}")
    print(f"       手法 {dict(Counter(c['method'] for c in COCKTAILS))}")
    avg = sum(len(c["text"]) for c in COCKTAILS) / len(COCKTAILS)
    print(f"       敘述平均 {avg:.0f} 字（不含材料表）")
    print()
    print(f"評估集 eval/eval_set.jsonl   {len(EVAL)} 題")
    print(f"       題型 {dict(Counter(e['type'] for e in EVAL))}")
    multi = sum(1 for e in EVAL if len(e["relevant"]) > 1)
    print(f"       多正解 {multi} 題（Recall@k 真正有意義的那些）")


if __name__ == "__main__":
    main()
