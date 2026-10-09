"""Server text in the owner's language: English (the source) or Arabic.

User-facing text is written in English. `tr()` returns it in the current language: the
panel sends its language in the Accept-Language header and `LanguageMiddleware` makes it the
current one for that request. Background work passes the shop's language explicitly.

Text that was produced in English earlier (a stored sync error, a wallet entry, an error
message raised deep in a service) is translated where it reaches the owner with
`localize()`, which also recognises templates with values filled in ("over the limit of
40,000 characters").
"""

import re
from contextvars import ContextVar
from typing import Literal

from starlette.types import ASGIApp, Receive, Scope, Send

Lang = Literal["en", "ar"]
LANGUAGES: tuple[Lang, ...] = ("en", "ar")

_current: ContextVar[Lang] = ContextVar("language", default="en")


def current() -> Lang:
    return _current.get()


def set_language(lang: str | None) -> None:
    _current.set(normalize_language(lang))


def normalize_language(value: str | None) -> Lang:
    return "ar" if value and value.strip().lower().startswith("ar") else "en"


def language_from_header(header: str | None) -> Lang:
    """The first language of an Accept-Language header that we speak ("ar-LB,ar;q=0.9")."""
    for part in (header or "").split(","):
        tag = part.split(";")[0].strip().lower()
        if tag.startswith("ar"):
            return "ar"
        if tag.startswith("en"):
            return "en"
    return "en"


def tr(template: str, lang: str | None = None, **params: object) -> str:
    """`template` (English, with {placeholders}) in the given or current language."""
    language = normalize_language(lang) if lang else current()
    text = AR.get(template, template) if language == "ar" else template
    return text.format(**params) if params else text


_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_patterns: list[tuple[re.Pattern[str], str]] | None = None


def _template_patterns() -> list[tuple[re.Pattern[str], str]]:
    global _patterns
    if _patterns is None:
        _patterns = []
        for template in AR:
            if not _PLACEHOLDER.search(template):
                continue
            regex = ""
            last = 0
            for match in _PLACEHOLDER.finditer(template):
                regex += re.escape(template[last : match.start()]) + f"(?P<{match.group(1)}>.+?)"
                last = match.end()
            regex += re.escape(template[last:])
            _patterns.append((re.compile(f"^{regex}$", re.DOTALL), template))
    return _patterns


def localize(text: str | None, lang: str | None = None) -> str | None:
    """English server text (stored, or raised as an error) in the given or current language."""
    if not text:
        return text
    language = normalize_language(lang) if lang else current()
    if language == "en":
        return text
    if text in AR:
        return AR[text]
    for pattern, template in _template_patterns():
        match = pattern.match(text)
        if match:
            return AR[template].format(**match.groupdict())
    # Several sentences joined (e.g. a teach result): translate each line on its own.
    if "\n" in text:
        return "\n".join(localize(line, language) or "" for line in text.split("\n"))
    return text


def minutes(count: int, lang: str | None = None) -> str:
    """'1 minute' / '3 minutes', with Arabic's plural forms."""
    language = normalize_language(lang) if lang else current()
    if language == "ar":
        if count == 1:
            return "دقيقة واحدة"
        if count == 2:
            return "دقيقتين"
        if 3 <= count <= 10:
            return f"{count} دقائق"
        return f"{count} دقيقة"
    return "1 minute" if count == 1 else f"{count} minutes"


class LanguageMiddleware:
    """Makes the request's Accept-Language the current language while it is handled."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            header = dict(scope.get("headers") or []).get(b"accept-language", b"")
            token = _current.set(language_from_header(header.decode("latin-1")))
            try:
                await self.app(scope, receive, send)
            finally:
                _current.reset(token)
            return
        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------- Arabic

AR: dict[str, str] = {
    # accounts and sign-in
    "Not authenticated": "لم يتم تسجيل الدخول",
    "Please confirm your email first, using the link we sent you": (
        "يرجى تأكيد بريدك الإلكتروني أولًا عبر الرابط الذي أرسلناه إليك"
    ),
    "This email is already registered": "هذا البريد الإلكتروني مسجّل مسبقًا",
    "Too many wrong passwords. Try again in {wait}, or use “Forgot password”.": (
        "أُدخلت كلمة مرور خاطئة عدة مرات. حاول مجددًا بعد {wait}، أو استخدم «نسيت كلمة المرور»."
    ),
    "Wrong email or password": "البريد الإلكتروني أو كلمة المرور غير صحيحة",
    "This account is disabled": "هذا الحساب معطّل",
    "Invalid token": "رمز غير صالح",
    "If this email is registered with Replisto, a password reset link is on its way.": (
        "إذا كان هذا البريد مسجّلًا في Replisto، فسيصلك رابط إعادة تعيين كلمة المرور."
    ),
    "This reset link is invalid or has expired. Please ask for a new one.": (
        "رابط إعادة التعيين غير صالح أو منتهي الصلاحية. يرجى طلب رابط جديد."
    ),
    "This confirmation link is invalid or has expired. Ask for a new one from the panel.": (
        "رابط التأكيد غير صالح أو منتهي الصلاحية. اطلب رابطًا جديدًا من اللوحة."
    ),
    "Your email is already confirmed.": "بريدك الإلكتروني مؤكَّد مسبقًا.",
    "Please try again in {wait}.": "يرجى المحاولة مجددًا بعد {wait}.",
    "A confirmation link was sent to {email}.": "أُرسل رابط التأكيد إلى {email}.",
    "Your current password is wrong": "كلمة المرور الحالية غير صحيحة",
    "Wrong password": "كلمة المرور غير صحيحة",
    "Please wait {wait} before asking for another code.": (
        "يرجى الانتظار {wait} قبل طلب رمز جديد."
    ),
    # emails and SMS
    "Reset your Replisto password": "إعادة تعيين كلمة مرور Replisto",
    "Hi,\n\nOpen this link to choose a new password:\n{link}\n\nThe link works once, for "
    "{minutes} minutes. If you didn't ask for this, you can ignore this email.\n\nReplisto": (
        "مرحبًا،\n\nافتح هذا الرابط لاختيار كلمة مرور جديدة:\n{link}\n\nيعمل الرابط مرة واحدة "
        "ولمدة {minutes} دقيقة. إذا لم تطلب ذلك، يمكنك تجاهل هذه الرسالة.\n\nReplisto"
    ),
    "Confirm your Replisto email": "تأكيد بريدك الإلكتروني في Replisto",
    "Hi,\n\nWelcome to Replisto! Open this link to confirm your email:\n{link}\n\nThe link "
    "works for {days} days. If you didn't sign up for Replisto, you can ignore this email."
    "\n\nReplisto": (
        "مرحبًا،\n\nأهلًا بك في Replisto! افتح هذا الرابط لتأكيد بريدك الإلكتروني:\n{link}\n\n"
        "يعمل الرابط لمدة {days} أيام. إذا لم تسجّل في Replisto، يمكنك تجاهل هذه الرسالة."
        "\n\nReplisto"
    ),
    "Your {app} verification code is {code}": "رمز التحقق في {app} هو {code}",
    # phone
    "Enter a valid mobile number, like 70 123 456 or +961 70 123 456.": (
        "أدخل رقم جوال صحيحًا، مثل 70 123 456 أو ‎+961 70 123 456."
    ),
    "This number is already verified on another Replisto account.": (
        "هذا الرقم مؤكَّد مسبقًا على حساب آخر في Replisto."
    ),
    "The code has expired. Please ask for a new one.": "انتهت صلاحية الرمز. يرجى طلب رمز جديد.",
    "Too many wrong codes. Please ask for a new one.": (
        "أُدخل رمز خاطئ عدة مرات. يرجى طلب رمز جديد."
    ),
    "That code isn't right.": "الرمز غير صحيح.",
    "We couldn't send the text message. Please try again in a few minutes.": (
        "تعذّر إرسال الرسالة النصية. يرجى المحاولة بعد بضع دقائق."
    ),
    "We couldn't send a text message to this number. Check it and try again.": (
        "تعذّر إرسال رسالة نصية إلى هذا الرقم. تحقّق منه وحاول مجددًا."
    ),
    # wallet and payments
    "Couldn't reach the payment provider. Please try again in a moment.": (
        "تعذّر الاتصال بمزوّد الدفع. يرجى المحاولة بعد قليل."
    ),
    "The payment provider isn't available right now. Please try again in a moment.": (
        "مزوّد الدفع غير متاح حاليًا. يرجى المحاولة بعد قليل."
    ),
    "The top-up amount must be between {min} and {max}.": "يجب أن يكون مبلغ الشحن بين {min} و{max}.",
    "Online card payments aren't set up yet. Please use another payment method.": (
        "الدفع بالبطاقة غير مفعّل بعد. يرجى استخدام طريقة دفع أخرى."
    ),
    "The payment provider sent an unexpected answer. Please try again.": (
        "أرسل مزوّد الدفع ردًا غير متوقع. يرجى المحاولة مجددًا."
    ),
    "This payment method isn't available.": "طريقة الدفع هذه غير متاحة.",
    "This transfer reference was already submitted.": "سبق إرسال رقم التحويل هذا.",
    "Wallet top-up": "شحن المحفظة",
    "Welcome gift": "هدية البداية",
    "Customer reply on Instagram": "رد على عميل في إنستغرام",
    "Learning shop information": "تعلّم معلومات المتجر",
    "Manual adjustment": "تسوية يدوية",
    # handoffs and conversations
    "The Replisto wallet is empty": "رصيد محفظة Replisto نفد",
    "The AI isn't set up": "الذكاء الاصطناعي غير مفعّل",
    "The bot couldn't find a suitable answer": "لم يجد البوت إجابة مناسبة",
    "This channel isn't connected right now; answer the customer in the app itself.": (
        "هذه القناة غير مربوطة حاليًا؛ أجب العميل من داخل التطبيق نفسه."
    ),
    "Sending the message failed; try again in a moment.": "فشل إرسال الرسالة؛ حاول بعد قليل.",
    "Message not found": "الرسالة غير موجودة",
    "Conversation not found": "المحادثة غير موجودة",
    "The last message must be from the customer": "يجب أن تكون الرسالة الأخيرة من العميل",
    "The AI service didn't respond. Please try again in a moment.": (
        "لم تستجب خدمة الذكاء الاصطناعي. يرجى المحاولة بعد قليل."
    ),
    "There's no message to answer": "لا توجد رسالة للرد عليها",
    # Instagram
    "Instagram is switched off on this server for now.": "إنستغرام متوقف على هذا الخادم حاليًا.",
    "Connect your Instagram account first.": "اربط حسابك على إنستغرام أولًا.",
    "Couldn't read your posts from Instagram. Please try again in a moment.": (
        "تعذّرت قراءة منشوراتك من إنستغرام. يرجى المحاولة بعد قليل."
    ),
    # shop information and files
    "This section holds a single text; use PUT /knowledge/single/{section}.": (
        "هذا القسم يحتوي على نص واحد فقط."
    ),
    "This section holds several entries.": "هذا القسم يحتوي على عدة عناصر.",
    "Entry not found": "العنصر غير موجود",
    "This would go over the limit of {limit} characters.": "سيتجاوز هذا الحد المسموح ({limit} حرف).",
    "The file is larger than {mb} MB.": "حجم الملف أكبر من {mb} ميغابايت.",
    "Reading images isn't available yet. Please type the text instead.": (
        "قراءة الصور غير متاحة بعد. يرجى كتابة النص بدلًا من ذلك."
    ),
    "Reading the image failed. Please try again.": "فشلت قراءة الصورة. يرجى المحاولة مجددًا.",
    "This file type isn't supported. Allowed formats: {allowed}": (
        "نوع الملف هذا غير مدعوم. الصيغ المسموحة: {allowed}"
    ),
    "No text was found in this file. If it's a scanned PDF, upload photos of the pages.": (
        "لم يُعثر على نص في هذا الملف. إذا كان ملف PDF ممسوحًا ضوئيًا، فارفع صور الصفحات."
    ),
    "Couldn't read the text file's encoding. Save it as UTF-8.": (
        "تعذّر التعرف على ترميز الملف النصي. احفظه بترميز UTF-8."
    ),
    "The PDF is damaged or password-protected.": "ملف PDF تالف أو محمي بكلمة مرور.",
    "Couldn't read the Word file.": "تعذّرت قراءة ملف Word.",
    # products
    "Product not found": "المنتج غير موجود",
    "This would go over the limit of {limit} products.": "سيتجاوز هذا الحد المسموح ({limit} منتج).",
    "Only .xlsx and .csv files are supported.": "ملفات ‎.xlsx و‎.csv فقط مدعومة.",
    "column_mapping must be JSON": "يجب أن يكون column_mapping بصيغة JSON",
    "Invalid column_mapping": "column_mapping غير صالح",
    "No Google Sheet is connected.": "لا يوجد Google Sheet مربوط.",
    "This product comes from your Google Sheet and is re-read from it every few minutes; "
    "change it in the sheet itself.": (
        "هذا المنتج مأخوذ من Google Sheet ويُقرأ منه كل بضع دقائق؛ عدّله في الجدول نفسه."
    ),
    "Invalid link.": "رابط غير صالح.",
    "Invalid Google Sheets link.": "رابط Google Sheets غير صالح.",
    "Invalid Google Drive link.": "رابط Google Drive غير صالح.",
    "Only Google Sheets links or Google Drive files are supported.": (
        "روابط Google Sheets وملفات Google Drive فقط مدعومة."
    ),
    "Couldn't reach Google. Please try again in a moment.": (
        "تعذّر الاتصال بـ Google. يرجى المحاولة بعد قليل."
    ),
    "The file isn't accessible. In Google Sheets, open Share and set “Anyone with the link” "
    "as Viewer.": (
        "الملف غير متاح. في Google Sheets افتح Share واختر «Anyone with the link» بصلاحية Viewer."
    ),
    "Google returned an error. Please try again in a moment.": (
        "أعاد Google خطأ. يرجى المحاولة بعد قليل."
    ),
    "The product file is too large.": "ملف المنتجات كبير جدًا.",
    "The table is empty, or its header row couldn't be found.": (
        "الجدول فارغ، أو تعذّر العثور على صف العناوين."
    ),
    "The table has {rows} rows, over the limit of {limit}.": (
        "يحتوي الجدول على {rows} صفًا، وهذا أكثر من الحد المسموح ({limit})."
    ),
    "Couldn't read the CSV file's encoding. Save it as UTF-8.": (
        "تعذّر التعرف على ترميز ملف CSV. احفظه بترميز UTF-8."
    ),
    "Couldn't read the Excel file.": "تعذّرت قراءة ملف Excel.",
    "Unknown field: {fields}": "حقل غير معروف: {fields}",
    "These columns aren't in the table: {columns}": "هذه الأعمدة غير موجودة في الجدول: {columns}",
    "Choose the “Product name” column.": "اختر عمود «اسم المنتج».",
    # teaching the bot
    "There was no text to read.": "لا يوجد نص للقراءة.",
    "The text is over the limit of {limit} characters. Split it into parts.": (
        "النص أطول من الحد المسموح ({limit} حرف). قسّمه إلى أجزاء."
    ),
    "The AI isn't set up on the server.": "الذكاء الاصطناعي غير مفعّل على الخادم.",
    "Your wallet is empty. Top it up to keep using this.": (
        "نفد رصيد محفظتك. اشحنها لمواصلة الاستخدام."
    ),
    "This proposal was already applied or discarded.": "سبق حفظ هذا الاقتراح أو تجاهله.",
    "Only applied changes can be undone.": "لا يمكن التراجع إلا عن التغييرات المحفوظة.",
    "Not found": "غير موجود",
    "Only Google Docs, Google Sheets and Google Drive file links are supported for now. You "
    "can also send the text directly.": (
        "روابط Google Docs وGoogle Sheets وملفات Google Drive فقط مدعومة حاليًا. "
        "ويمكنك أيضًا إرسال النص مباشرة."
    ),
    "This Google link can't be read.": "تعذّرت قراءة رابط Google هذا.",
    "The file isn't accessible. In Google, open Share and set “Anyone with the link” as "
    "Viewer.": "الملف غير متاح. في Google افتح Share واختر «Anyone with the link» بصلاحية Viewer.",
    "The file is too large.": "الملف كبير جدًا.",
    "Undone.": "تم التراجع.",
    "Nothing was changed.": "لم يتغيّر شيء.",
    "{n} product added": "أُضيف منتج واحد",
    "{n} products added": "أُضيف {n} منتجات",
    "{n} product updated": "حُدّث منتج واحد",
    "{n} products updated": "حُدّث {n} منتجات",
    "{n} product removed": "حُذف منتج واحد",
    "{n} products removed": "حُذف {n} منتجات",
    "{n} shop information entry saved": "حُفظ عنصر واحد في معلومات المتجر",
    "{n} shop information entries saved": "حُفظ {n} عناصر في معلومات المتجر",
    "{n} from your Google Sheet (change those in the sheet itself)": (
        "{n} من Google Sheet (عدّلها في الجدول نفسه)"
    ),
    "{n} skipped (over the limit or already removed)": "تُخطّي {n} (تجاوز الحد أو حُذف مسبقًا)",
    "no price": "بلا سعر",
    "stock {n}": "المخزون {n}",
    "🗑 Remove: {product}": "🗑 حذف: {product}",
    " 🔒 (change it in the Google Sheet)": " 🔒 (عدّله في Google Sheet)",
    "Price": "السعر",
    "Stock": "المخزون",
    "Name": "الاسم",
    "Colour": "اللون",
    "Size": "المقاس",
    "Description": "الوصف",
    "Category": "الفئة",
    "SKU": "الرمز",
    "… and {n} more": "… و{n} عناصر أخرى",
    "updated": "سيُحدَّث",
    "added": "سيُضاف",
    "🔄 Live Google Sheet connection ({rows} rows); it's re-read every few minutes.": (
        "🔄 ربط مباشر مع Google Sheet ({rows} صف)؛ يُقرأ مجددًا كل بضع دقائق."
    ),
    "I didn't find anything new to learn.": "لم أجد شيئًا جديدًا للتعلّم.",
    "Google Doc": "Google Doc",
    "Google Sheet": "Google Sheet",
    "Google Drive file": "ملف Google Drive",
    "This Google Sheet is a product list. I matched the columns like this: {labels}": (
        "هذا الـ Google Sheet قائمة منتجات. طابقتُ الأعمدة هكذا: {labels}"
    ),
    "The Google Sheet wasn't connected.": "لم يُربط Google Sheet.",
    "Reading the Google Sheet failed: {error}": "فشلت قراءة Google Sheet: {error}",
    "The Google Sheet is connected and {count} product rows were read.": (
        "رُبط Google Sheet وقُرئ {count} صف من المنتجات."
    ),
    # knowledge sections (labels as the API sends them)
    "About the shop": "عن المتجر",
    "Shipping": "الشحن",
    "Payment": "الدفع",
    "Returns and exchanges": "الإرجاع والاستبدال",
    "Contact and opening hours": "التواصل وساعات العمل",
    "Frequently asked questions": "الأسئلة الشائعة",
    "Other details": "معلومات أخرى",
    "Uploaded files": "الملفات المرفوعة",
    # product fields (labels as the API sends them)
    "Product name": "اسم المنتج",
    "Instagram post link": "رابط منشور إنستغرام",
    # emails
    "Welcome to Replisto!": "أهلًا بك في Replisto!",
    "Tap the button to confirm your email address.": "اضغط على الزر لتأكيد بريدك الإلكتروني.",
    "Confirm my email": "تأكيد بريدي الإلكتروني",
    "The link works for {days} days. If you didn't sign up for Replisto, you can ignore this email.": "يعمل الرابط لمدة {days} أيام. إذا لم تسجّل في Replisto، يمكنك تجاهل هذه الرسالة.",
    "Choose a new password": "اختر كلمة مرور جديدة",
    "Tap the button to choose a new password for your Replisto account.": "اضغط على الزر لاختيار كلمة مرور جديدة لحسابك في Replisto.",
    "The link works once, for {minutes} minutes. If you didn't ask for this, you can ignore this email.": "يعمل الرابط مرة واحدة لمدة {minutes} دقيقة. إذا لم تطلب ذلك، يمكنك تجاهل هذه الرسالة.",
    "A customer is waiting for you": "زبون بانتظارك",
    "A customer": "زبون",
    "{customer} asked something the assistant couldn't answer. Reply from your panel:": "سأل {customer} عن شيء لم يستطع المساعد الإجابة عنه. ردّ عليه من لوحتك:",
    "Open the conversation": "افتح المحادثة",
    "Your Replisto wallet is running low": "رصيد محفظتك في Replisto منخفض",
    "Your balance is {balance}. Top it up so the assistant keeps answering your customers.": "رصيدك {balance}. اشحن المحفظة ليبقى المساعد يردّ على زبائنك.",
    "Your Replisto wallet is empty": "محفظتك في Replisto فارغة",
    "The assistant has stopped answering customers and is passing their messages to you. Top up to turn it back on.": "توقف المساعد عن الرد على الزبائن ويحوّل رسائلهم إليك. اشحن المحفظة لتشغيله من جديد.",
    "Top up": "اشحن المحفظة",
    "You get these emails because you run {shop} on Replisto.": "تصلك هذه الرسائل لأنك تدير {shop} على Replisto.",
    # the website assistant
    "The assistant isn't available right now.": "المساعد غير متاح حاليًا.",
    "A little slower please, try again in a few seconds.": "على مهلك قليلًا، حاول مجددًا بعد ثوانٍ.",
    "Today's chat allowance is used up. Create a free account for more.": "انتهت حصة المحادثة لهذا اليوم. أنشئ حسابًا مجانيًا لتحصل على المزيد.",
    "Today's chat allowance is used up.": "انتهت حصة المحادثة لهذا اليوم.",
    "This chat link isn't valid. Please reload the page.": "رابط المحادثة غير صالح. يرجى إعادة تحميل الصفحة.",
    "The assistant is busy right now, please ask again in a moment.": "المساعد مشغول الآن، اسأل مجددًا بعد قليل.",
    "Comment replies are switched off": "الرد على التعليقات متوقف",
    "The bot is switched off": "البوت متوقف",
    "Instagram isn't connected": "إنستغرام غير مربوط",
    "Instagram didn't accept the reply": "لم يقبل إنستغرام الرد",
    "The AI couldn't read this comment": "لم يتمكن الذكاء الاصطناعي من قراءة هذا التعليق",
    "The bot couldn't decide on an answer": "لم يتمكن البوت من تحديد الرد",
    "Instagram allows only one private reply per comment.": "يسمح إنستغرام بردّ خاص واحد فقط لكل تعليق.",
    "Instagram didn't accept the reply. Private replies work within 7 days of the comment.": "لم يقبل إنستغرام الرد. الرد الخاص متاح خلال 7 أيام من التعليق.",
    "Instagram didn't accept the change. Please try again.": "لم يقبل إنستغرام التغيير. يرجى المحاولة مجددًا.",
    "Comment not found": "التعليق غير موجود",
    "This comment was already answered": "تم الرد على هذا التعليق من قبل",
    "Unknown category": "تصنيف غير معروف",
    "The AI service isn't responding right now. Please try again in a moment.": "خدمة الذكاء الاصطناعي لا تستجيب الآن. يرجى المحاولة بعد قليل.",
    "Reconnect Instagram and allow publishing to post stories": "أعد ربط إنستغرام واسمح بالنشر لتُنشر القصص",
    "Instagram couldn't process this file": "لم يتمكن إنستغرام من معالجة هذا الملف",
    "Instagram didn't accept this story": "لم يقبل إنستغرام هذه القصة",
    "Instagram took too long to process this video": "استغرق إنستغرام وقتًا طويلًا في معالجة هذا الفيديو",
    "Upload a photo (JPG, PNG, WebP) or a video (MP4, MOV).": "ارفع صورة (JPG أو PNG أو WebP) أو فيديو (MP4 أو MOV).",
    "Choose a time in the future.": "اختر وقتًا في المستقبل.",
    "Stories can be scheduled up to 60 days ahead.": "يمكن جدولة القصص حتى 60 يومًا مقدّمًا.",
    "This photo is too large.": "هذه الصورة كبيرة جدًا.",
    "This photo is too small; use at least 320 pixels on each side.": "هذه الصورة صغيرة جدًا؛ استخدم 320 بكسل على الأقل لكل جهة.",
    "This video is too large; stories take videos up to 100 MB.": "هذا الفيديو كبير جدًا؛ القصص تقبل فيديوهات حتى 100 ميغابايت.",
    "This video couldn't be read. Use an MP4 or MOV file.": "تعذّرت قراءة هذا الفيديو. استخدم ملف MP4 أو MOV.",
    "This photo couldn't be read. Try a JPG or PNG file.": "تعذّرت قراءة هذه الصورة. جرّب ملف JPG أو PNG.",
    "This file is too large.": "هذا الملف كبير جدًا.",
    "Story not found": "القصة غير موجودة",
    "This story is already on its way to Instagram.": "هذه القصة في طريقها إلى إنستغرام بالفعل.",
    "Read your page's numbers first.": "اقرأ أرقام صفحتك أولًا.",
    "The AI isn't set up on this server yet.": "الذكاء الاصطناعي غير مُعدّ على هذا الخادم بعد.",
    "Your wallet is empty. Top up to use the content assistant.": "محفظتك فارغة. اشحنها لاستخدام مساعد المحتوى.",
    "The content assistant is busy. Please try again in a moment.": "مساعد المحتوى مشغول. يرجى المحاولة بعد قليل.",
    "Couldn't read your page's numbers from Instagram. Please try again in a moment.": "تعذّرت قراءة أرقام صفحتك من إنستغرام. يرجى المحاولة بعد قليل.",
    "Couldn't read the page's numbers from Instagram": "تعذّرت قراءة أرقام الصفحة من إنستغرام",
    "Reconnect Instagram and allow access to insights.": "أعد ربط إنستغرام واسمح بالوصول إلى الإحصاءات.",
    "The last message must be yours.": "يجب أن تكون الرسالة الأخيرة منك.",
}
