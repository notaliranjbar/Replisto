// Copy added with the panel redesign (navigation groups, page intros, helper text).

const panel = {
  nav: {
    groupMessages: "المحادثات",
    groupTrain: "تدريب البوت",
    groupSetup: "الإعدادات",
    home: "الرئيسية",
    handoffs: "التحويلات",
    inbox: "الرسائل",
    test: "اختبار",
    more: "المزيد",
    main: "قائمة اللوحة",
    closeMenu: "إغلاق القائمة",
  },

  dashboard: {
    greeting: (name: string) => `مرحبًا، ${name}`,
    offHint: "شغّله ليتمكن من التحدث مع عملائك.",
    quickTitle: "اختصارات",
    quick: {
      playground: { title: "اختبار البوت", body: "اطرح الأسئلة كعميل وشاهد الردود." },
      knowledge: { title: "معلومات المتجر", body: "كلما كانت أكمل، كانت ردود البوت أفضل." },
      inbox: { title: "صندوق الرسائل", body: "أحدث محادثات العملاء." },
      settings: { title: "الأسلوب والقواعد", body: "كيف يتحدث البوت وما الذي لا يفعله." },
    },
    usageTitle: "استهلاك هذا الشهر",
  },

  knowledge: {
    navTitle: "الأقسام",
    filled: "مكتمل",
    empty: "فارغ",
    drop: "أفلت الملف هنا",
    or: "أو",
    choose: "اختيار ملف",
  },

  playground: {
    env: "بيئة الاختبار",
    botName: (shop: string) => `بوت ${shop}`,
    tipsTitle: "ماذا أجرّب؟",
    tips: ["الأسئلة التي يطرحها العملاء كثيرًا", "مخزون أو سعر منتج محدد", "سؤال لم تعطِ البوت إجابته"],
    safe: "لا تُرسل أي رسالة لأحد ولا تُحفظ؛ ويعمل حتى عندما يكون البوت متوقفًا.",
    improveTitle: "حسّن الردود",
  },

  settings: {
    sections: {
      status: { title: "الحالة", desc: "تشغيل Replisto أو إيقافه لجميع المحادثات." },
      identity: { title: "التعريف", desc: "الاسم الذي يقدّم البوت نفسه به في المحادثة." },
      tone: { title: "الأسلوب", desc: "كيف يتحدث البوت مع العملاء. شاهد مثالًا لكل أسلوب." },
      fallback: { title: "عندما لا يعرف الإجابة", desc: "الرسالة التي تُرسل عند تحويل المحادثة إليك." },
      rules: { title: "القواعد", desc: "خطوط حمراء لا يتجاوزها البوت أبدًا." },
      handoff: { title: "عندما ترد بنفسك", desc: "يصمت البوت مع ذلك العميل لفترة حتى لا يقاطعك." },
    },
    discard: "تراجع",
    sample: "مثال",
  },

  instagram: {
    stepsTitle: "أمران قبل الربط",
    howItWorks: "يتم الربط من صفحة إنستغرام الرسمية ولا حاجة لكلمة مرور الصفحة.",
  },

  notFound: {
    hint: "هذه الصفحة غير موجودة أو تم نقلها.",
  },
};

export default panel;
