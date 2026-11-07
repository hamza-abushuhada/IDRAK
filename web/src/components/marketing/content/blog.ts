export type Block =
  | { t: "p"; text: string }
  | { t: "h2"; text: string }
  | { t: "ul"; items: string[] }
  | { t: "note"; text: string }
  | { t: "quote"; text: string };

export type Article = {
  slug: string;
  date: string;
  minutes: number;
  tag: { en: string; ar: string };
  en: { title: string; dek: string; body: Block[] };
  ar: { title: string; dek: string; body: Block[] };
};

export const ARTICLES: Article[] = [
  {
    slug: "why-your-pos-reports-lie",
    date: "2026-10-20",
    minutes: 6,
    tag: { en: "Data cleaning", ar: "تنظيف البيانات" },
    en: {
      title: "Why your POS reports lie to you",
      dek: "Your point-of-sale system adds up exactly what it was given. The trouble is what it was given.",
      body: [
        { t: "p", text: "Every month, thousands of shop owners in Jordan open a sales report, look at the top ten products, and make decisions: what to reorder, what to discount, what to stop stocking. Most of those reports are wrong. Not because the POS is broken, but because the data going into it is messy in ways no report is designed to notice." },
        { t: "h2", text: "One product, many names" },
        { t: "p", text: "When three cashiers enter the same can as بيبسي 330, ببسي and PEPSI 330ML, your report shows three products with modest sales instead of one bestseller. The real top seller drops out of your top ten, and you reorder it late. In the sample files we've looked at, roughly one product row in four was a duplicate or a spelling variant of another." },
        { t: "ul", items: ["Alef variants: أ, إ, آ and ا written interchangeably", "Taa marbuta and haa: لبنة vs لبنه", "Yaa and alef maqsura: المراعي vs المراعى", "Arabic and English names for the same item"] },
        { t: "h2", text: "Fils that look like dinars" },
        { t: "p", text: "A price typed as 350 instead of 0.350 turns a can of soda into a 350-dinar item. One line like that can inflate a day's revenue a thousand times over — or, if the system rejects it silently, make a sale disappear. Because Jordanian prices have three decimals, this mistake is common and easy to miss." },
        { t: "h2", text: "Dates in three calendars" },
        { t: "p", text: "Arabic-Indic digits (١٥/٠٣/٢٠٢٦), Hijri dates (15 رمضان 1447) and American-style 3/15/26 can all appear in the same column. Spreadsheets treat many of them as text, so they quietly fall out of any month-by-month comparison." },
        { t: "note", text: "A quick test: sort your product list alphabetically and scroll. If you see the same item twice within a few rows, your sales-by-product report is splitting it." },
        { t: "h2", text: "What to do about it" },
        { t: "p", text: "You don't need to retype anything. Start by measuring the problem: how many duplicates, how many invalid prices, how many dates that can't be read. That's what Idrak's free Data Health Check does in about a minute. Then fix the data once, keep a record of every change, and let the same rules run on next month's export automatically." },
      ],
    },
    ar: {
      title: "ليش تقارير نقاط البيع عم تكذب عليك",
      dek: "نظام نقاط البيع بيجمع بالزبط اللي انعطى إله. المشكلة باللي انعطى إله.",
      body: [
        { t: "p", text: "كل شهر، آلاف أصحاب المحلات في الأردن بيفتحوا تقرير المبيعات، بيشوفوا أعلى عشر أصناف، وبياخدوا قرارات: شو يطلبوا، شو يخصموا، وشو يوقّفوا. أغلب هالتقارير غلط. مش لأنه النظام خربان، بل لأنه البيانات اللي داخلة عليه مخربطة بطرق ما في تقرير مصمّم ينتبهلها." },
        { t: "h2", text: "صنف واحد، أسامي كثير" },
        { t: "p", text: "لما ثلاث كاشيرية يدخّلوا نفس العلبة كـ بيبسي 330 وببسي وPEPSI 330ML، التقرير بيطلعلك ثلاث أصناف مبيعها متوسط بدل صنف واحد هو الأكثر مبيعاً. الصنف الحقيقي بيطلع من قائمة العشرة الأوائل، وبتتأخر بطلبه. بعيّنات الملفات اللي شفناها، تقريباً صف من كل أربع صفوف أصناف كان مكرّر أو مكتوب بشكل مختلف." },
        { t: "ul", items: ["أشكال الألف: أ، إ، آ، ا بتنكتب مكان بعض", "التاء المربوطة والهاء: لبنة ولبنه", "الياء والألف المقصورة: المراعي والمراعى", "اسم عربي واسم إنجليزي لنفس الصنف"] },
        { t: "h2", text: "فلوس شكلها دنانير" },
        { t: "p", text: "سعر مكتوب 350 بدل 0.350 بيحوّل علبة المشروب الغازي لصنف حقّه 350 دينار. سطر واحد مثل هيك ممكن يضخّم إيراد يوم كامل ألف مرة — أو، إذا النظام رفضه بصمت، يخفي بيعة. ولأنه الأسعار بالأردن إلها ثلاث خانات عشرية، هالغلطة شائعة وسهل ما تنتبهلها." },
        { t: "h2", text: "تواريخ بثلاث تقاويم" },
        { t: "p", text: "أرقام عربية (١٥/٠٣/٢٠٢٦)، وتواريخ هجرية (15 رمضان 1447)، وصيغة أمريكية 3/15/26 — كلها ممكن تكون بنفس العمود. الجداول بتتعامل مع كثير منها كنص، فبتطلع بهدوء من أي مقارنة شهرية." },
        { t: "note", text: "اختبار سريع: رتّب قائمة أصنافك أبجدياً وانزل فيها. إذا شفت نفس الصنف مرتين خلال كم سطر، فتقرير المبيعات حسب الصنف عم يقسمه." },
        { t: "h2", text: "شو الحل؟" },
        { t: "p", text: "مش لازم تعيد كتابة إشي. ابدأ بقياس المشكلة: قديش في تكرار، قديش في أسعار غلط، وقديش في تواريخ ما بتنقرأ. وهذا بالزبط اللي بيعمله فحص صحة البيانات المجاني من إدراك بحوالي دقيقة. بعدها صلّح البيانات مرة وحدة، واحتفظ بسجل لكل تعديل، وخلّي نفس القواعد تشتغل لحالها على ملف الشهر الجاي." },
      ],
    },
  },
  {
    slug: "ramadan-stock-planning",
    date: "2026-11-03",
    minutes: 7,
    tag: { en: "Forecasting", ar: "التوقّعات" },
    en: {
      title: "Ramadan stock planning for mini-markets",
      dek: "Ramadan moves every year, and so does demand. Last year's sales are your best guide — if you line them up with the right calendar.",
      body: [
        { t: "p", text: "Ramadan 1448 is expected to begin around 8 February 2027, subject to the moon sighting. For a mini-market, the weeks before and during the month can bring the biggest swings of the year: some categories double, others go quiet, and the last ten nights and Eid behave differently again." },
        { t: "h2", text: "Compare Ramadan with Ramadan, not February with February" },
        { t: "p", text: "Because the Hijri calendar moves about eleven days earlier each year, comparing this February with last February mixes Ramadan days with ordinary ones. Line up last year's sales by Hijri date instead: the first days of Ramadan with the first days of Ramadan, the last ten nights with the last ten nights." },
        { t: "h2", text: "Categories that usually move" },
        { t: "ul", items: ["Dates, qamar el-din, Vimto and other drink concentrates", "Flour, sugar, oil, rice and lentils for home cooking", "Laban, labneh and dairy for suhoor", "Sweets, nuts and chocolate in the run-up to Eid"] },
        { t: "p", text: "Your own shop may differ — a mini-market near offices behaves differently from one in a residential street. That's exactly why your own history matters more than any general list." },
        { t: "h2", text: "Plan reorders around supplier lead times" },
        { t: "p", text: "Many suppliers get busy in the two weeks before Ramadan. Work backwards from the first day: if a supplier takes five days to deliver and you want stock on the shelf three days early, your order goes out eight days before. Do the same for the Eid peak." },
        { t: "note", text: "Watch the after-Eid hangover. Over-ordering for Eid is one of the most common sources of dead stock we see in the following months." },
        { t: "h2", text: "Where Idrak helps" },
        { t: "p", text: "Idrak's forecast knows when Ramadan and both Eids fall, compares like with like across years, and suggests reorder quantities per branch. When you approve a plan, it drafts the email to each supplier. You stay in control of the final numbers." },
      ],
    },
    ar: {
      title: "تخطيط بضاعة رمضان للميني ماركت",
      dek: "رمضان بيتحرّك كل سنة، والطلب كمان. مبيعات السنة الماضية أحسن دليل إلك — إذا رتّبتها على التقويم الصح.",
      body: [
        { t: "p", text: "من المتوقّع إنه يبلّش رمضان 1448 حوالي 8 شباط 2027، حسب رؤية الهلال. بالنسبة للميني ماركت، الأسابيع اللي قبل الشهر وخلاله ممكن تجيب أكبر تقلّبات بالسنة: أصناف بتتضاعف، وأصناف بتهدى، والعشر الأواخر والعيد إلهم سلوك مختلف كمان." },
        { t: "h2", text: "قارن رمضان برمضان، مش شباط بشباط" },
        { t: "p", text: "لأنه التقويم الهجري بيتقدّم حوالي إحدعش يوم كل سنة، مقارنة شباط هالسنة بشباط الماضي بتخلط أيام رمضان بأيام عادية. رتّب مبيعات السنة الماضية حسب التاريخ الهجري: أول أيام رمضان مع أول أيام رمضان، والعشر الأواخر مع العشر الأواخر." },
        { t: "h2", text: "أصناف عادةً بتتحرّك" },
        { t: "ul", items: ["التمر وقمر الدين والفيمتو وباقي المشروبات المركّزة", "الطحين والسكر والزيت والرز والعدس للطبخ البيتي", "اللبن واللبنة والألبان للسحور", "الحلويات والمكسرات والشوكولاتة قبل العيد"] },
        { t: "p", text: "محلّك ممكن يكون مختلف — الميني ماركت اللي جنب المكاتب غير اللي بشارع سكني. وعشان هيك تاريخ مبيعات محلّك أهم من أي قائمة عامة." },
        { t: "h2", text: "خطّط الطلبيات حسب مدة توريد الموردين" },
        { t: "p", text: "كثير موردين بينشغلوا بالأسبوعين اللي قبل رمضان. احسبها بالعكس من أول يوم: إذا المورّد بياخد خمس أيام ليوصّل، وبدّك البضاعة على الرف قبل بثلاث أيام، يعني طلبيتك لازم تطلع قبل بثمان أيام. واعمل نفس الإشي لذروة العيد." },
        { t: "note", text: "انتبه لما بعد العيد. الطلب الزيادة للعيد من أكثر الأسباب اللي بنشوفها للبضاعة الواقفة بالأشهر اللي بعده." },
        { t: "h2", text: "وين بيساعد إدراك" },
        { t: "p", text: "توقّعات إدراك بتعرف إمتى رمضان والعيدين، وبتقارن الفترات المتشابهة عبر السنين، وبتقترح كميات الطلب لكل فرع. ولما تعتمد الخطة، بتجهّز الإيميل لكل مورّد. والقرار النهائي بالأرقام بيضل إلك." },
      ],
    },
  },
  {
    slug: "jofotara-e-invoicing-readiness",
    date: "2026-09-28",
    minutes: 8,
    tag: { en: "Compliance", ar: "الامتثال" },
    en: {
      title: "Preparing your shop for Jordan e-invoicing (JoFotara)",
      dek: "A plain-language checklist for getting your sales data ready for the national e-invoicing system.",
      body: [
        { t: "note", text: "This article is general guidance, not tax or legal advice. Requirements, deadlines and technical details change. Always check the official Income and Sales Tax Department (ISTD) sources or a licensed accountant before acting." },
        { t: "p", text: "Jordan's Income and Sales Tax Department has been rolling out a national electronic invoicing system, commonly known as JoFotara (جو فوترة). The aim is for invoices to be issued and reported in a standard electronic format. Which businesses must comply, and from when, depends on the rules ISTD publishes for each category of taxpayer." },
        { t: "h2", text: "Why your data matters before the software does" },
        { t: "p", text: "Whether you connect your POS directly or use the official portal, an electronic invoice can only be as good as the data behind it. Missing tax numbers, inconsistent product names, gaps in invoice sequences and wrong tax rates are much easier to fix in advance than after invoices start being rejected." },
        { t: "h2", text: "A readiness checklist" },
        { t: "ul", items: ["Your own registration details and tax number are correct and match your official records", "Business customers' tax numbers are recorded where required", "Every product has a clear name and the right sales tax treatment", "Invoice numbers are continuous, with no unexplained gaps or duplicates", "Returns and credit notes are linked to the original invoice", "Prices and totals use consistent decimals (JOD has three)"] },
        { t: "h2", text: "Talk to your POS provider early" },
        { t: "p", text: "Ask whether your current system supports e-invoicing integration, what it costs, and what you need to prepare. If your provider has a timeline, put it in your calendar alongside the official deadlines that apply to you." },
        { t: "h2", text: "Where Idrak helps" },
        { t: "p", text: "Idrak's compliance check (on the Business plan) scans your sales and invoice data for the kinds of problems above — missing tax numbers, sequence gaps, inconsistent tax treatment — and shows you exactly which records to fix. It doesn't submit invoices for you and doesn't replace your accountant; it helps you arrive prepared." },
      ],
    },
    ar: {
      title: "جهّز محلّك للفوترة الإلكترونية في الأردن (جو فوترة)",
      dek: "قائمة تحقّق بلغة بسيطة عشان تكون بيانات مبيعاتك جاهزة لنظام الفوترة الوطني الإلكتروني.",
      body: [
        { t: "note", text: "هذا المقال إرشاد عام، مش استشارة ضريبية أو قانونية. المتطلبات والمواعيد والتفاصيل الفنية بتتغيّر. ارجع دايماً للمصادر الرسمية لدائرة ضريبة الدخل والمبيعات أو لمحاسب قانوني قبل ما تتصرّف." },
        { t: "p", text: "دائرة ضريبة الدخل والمبيعات الأردنية عم تطبّق نظام فوترة وطني إلكتروني، معروف باسم «جو فوترة». الهدف إنه الفواتير تنصدر وتنبلّغ بصيغة إلكترونية موحّدة. ومين ملزم، ومن إمتى، بيعتمد على القواعد اللي بتنشرها الدائرة لكل فئة من المكلّفين." },
        { t: "h2", text: "ليش بياناتك أهم من البرنامج" },
        { t: "p", text: "سواء ربطت نظام نقاط البيع مباشرة أو استخدمت البوابة الرسمية، الفاتورة الإلكترونية جودتها من جودة البيانات اللي وراها. أرقام ضريبية ناقصة، أسماء أصناف مش متّسقة، فجوات بتسلسل الفواتير، ونسب ضريبة غلط — كلها أسهل بكثير تتصلّح بدري من بعد ما تبلّش الفواتير تنرفض." },
        { t: "h2", text: "قائمة الجاهزية" },
        { t: "ul", items: ["بيانات تسجيلك ورقمك الضريبي صحيحة ومطابقة لسجلاتك الرسمية", "الأرقام الضريبية لزبائنك من الشركات مسجّلة لما يكون مطلوب", "كل صنف إله اسم واضح ومعاملة ضريبة مبيعات صحيحة", "أرقام الفواتير متسلسلة، بدون فجوات أو تكرار غير مفسَّر", "المرتجعات والإشعارات الدائنة مربوطة بالفاتورة الأصلية", "الأسعار والمجاميع بخانات عشرية ثابتة (الدينار إله ثلاث خانات)"] },
        { t: "h2", text: "احكِ مع مزوّد نظام نقاط البيع بدري" },
        { t: "p", text: "اسأله إذا نظامك الحالي بيدعم الربط مع الفوترة الإلكترونية، وقديش الكلفة، وشو لازم تجهّز. وإذا عنده جدول زمني، حطّه بتقويمك جنب المواعيد الرسمية اللي بتنطبق عليك." },
        { t: "h2", text: "وين بيساعد إدراك" },
        { t: "p", text: "فحص الامتثال في إدراك (بباقة الأعمال) بيفحص بيانات مبيعاتك وفواتيرك عن هالنوع من المشاكل — أرقام ضريبية ناقصة، فجوات بالتسلسل، معاملة ضريبية مش متّسقة — وبيورجيك بالزبط أي سجلات لازم تتصلّح. ما بيبعت الفواتير عنك وما بيغني عن محاسبك؛ بيساعدك توصل جاهز." },
      ],
    },
  },
];

export const getArticle = (slug: string) => ARTICLES.find((a) => a.slug === slug);
