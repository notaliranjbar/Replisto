import type { Section } from "../api/types";
import type { Lang } from ".";

// Section labels come from the API in English; the panel swaps in its own translations.
// Unknown keys fall back to the API text.
type Copy = Record<string, Pick<Section, "label" | "hint" | "placeholder">>;

const en: Copy = {
  about: {
    label: "About the shop",
    hint: "What does your shop sell, and what should customers know about it?",
    placeholder: "e.g. Layla Boutique in Achrafieh, making women's dresses and blouses since 2019. Everything is sewn in-house.",
  },
  shipping: {
    label: "Shipping",
    hint: "Shipping methods, cost, delivery time, other cities and abroad",
    placeholder: "e.g. Delivery all over Lebanon in 2–3 working days for $4; same day in Beirut. Free over $100.",
  },
  payment: {
    label: "Payment",
    hint: "Payment methods and how to place an order",
    placeholder: "e.g. Cash on delivery (dollars or lira), or Whish Money before delivery.",
  },
  returns: {
    label: "Returns & exchanges",
    hint: "Return or exchange conditions and deadline",
    placeholder: "e.g. Size exchanges within 7 days of delivery if unworn with tags.",
  },
  contact: {
    label: "Contact & opening hours",
    hint: "Website, phone, address, support hours",
    placeholder: "e.g. layla.shop, Achrafieh, open 10am–7pm, closed Sundays.",
  },
  faq: {
    label: "Frequently asked questions",
    hint: "Questions customers often ask, with the answers",
    placeholder: "Question: What's the fabric? / Answer: Premium Turkish linen",
  },
  free_text: {
    label: "Other information",
    hint: "Anything else the bot should know",
    placeholder: "e.g. 15% off your first order with code FIRST15",
  },
  file: {
    label: "Uploaded files",
    hint: "Text extracted from your files. You can edit it.",
    placeholder: "",
  },
};

const ar: Copy = {
  about: {
    label: "عن المتجر",
    hint: "ماذا يبيع متجرك، وما الذي يجب أن يعرفه العملاء عنه؟",
    placeholder: "مثلًا: بوتيك نورة في الأشرفية، نصمم الفساتين والبلوزات النسائية منذ 2019. كل القطع تُخاط لدينا.",
  },
  shipping: {
    label: "الشحن",
    hint: "طرق الشحن والتكلفة ومدة التوصيل والمدن الأخرى والخارج",
    placeholder: "مثلًا: توصيل لكل لبنان خلال 2 إلى 3 أيام عمل بـ 4 دولارات، وبنفس اليوم داخل بيروت. مجاني للطلبات فوق 100 دولار.",
  },
  payment: {
    label: "الدفع",
    hint: "طرق الدفع وكيفية تقديم الطلب",
    placeholder: "مثلًا: الدفع عند الاستلام (بالدولار أو الليرة)، أو عبر Whish Money قبل التوصيل.",
  },
  returns: {
    label: "الإرجاع والاستبدال",
    hint: "شروط الإرجاع أو الاستبدال ومدته",
    placeholder: "مثلًا: استبدال المقاس خلال 7 أيام من الاستلام إذا لم يُلبس وكانت البطاقة سليمة.",
  },
  contact: {
    label: "التواصل وساعات العمل",
    hint: "الموقع والهاتف والعنوان وساعات الدعم",
    placeholder: "مثلًا: noura.shop، الأشرفية، من 10 صباحًا حتى 7 مساءً، مغلق يوم الأحد.",
  },
  faq: {
    label: "الأسئلة الشائعة",
    hint: "أسئلة يطرحها العملاء كثيرًا، مع إجاباتها",
    placeholder: "السؤال: ما نوع القماش؟ / الإجابة: كتان تركي فاخر",
  },
  free_text: {
    label: "معلومات أخرى",
    hint: "أي شيء آخر يجب أن يعرفه البوت",
    placeholder: "مثلًا: خصم 15% على طلبك الأول بالرمز FIRST15",
  },
  file: {
    label: "الملفات المرفوعة",
    hint: "النص المستخرج من ملفاتك. يمكنك تعديله.",
    placeholder: "",
  },
};

const copies: Record<Lang, Copy> = { en, ar };

export function localizeSection(section: Section, lang: Lang): Section {
  const tr = copies[lang][section.key];
  return tr ? { ...section, ...tr } : section;
}
