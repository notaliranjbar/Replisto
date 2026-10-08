import { useEffect, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { useAuth } from "../../auth/AuthContext";
import SiteFooter from "../../components/site/SiteFooter";
import SiteHeader from "../../components/site/SiteHeader";
import { cx } from "../../components/ui";
import { useI18n, type Lang } from "../../i18n";

// Public legal pages (no login): for owners and their customers, for the payment provider's
// review, and for Meta's app review. Every page has full English and Arabic versions;
// `?lang=en` / `?lang=ar` opens one directly. Every statement here must match what the
// product actually does: change the page when the product changes.

const SUPPORT_EMAIL = import.meta.env.VITE_SUPPORT_EMAIL || "support@replisto.app";
const UPDATED = "2026-10-08";

type Page = { title: Record<Lang, string>; body: Record<Lang, ReactNode> };

function LegalShell({ page }: { page: Page }) {
  const { t, lang, f } = useI18n();
  const { loggedIn } = useAuth();
  const { pathname, hash } = useLocation();
  useEffect(() => {
    document.title = `${page.title[lang]} · ${t.appName}`;
  }, [page, lang, t]);
  // /terms#wallet (from the top-up form): the page loads lazily, so scroll once it's there.
  useEffect(() => {
    if (!hash) return;
    // after the app's own scroll-to-top on navigation
    const timer = setTimeout(() => document.getElementById(hash.slice(1))?.scrollIntoView(), 100);
    return () => clearTimeout(timer);
  }, [hash]);
  const links = [
    ["/privacy", t.legal.privacy],
    ["/terms", t.legal.terms],
    ["/data-deletion", t.legal.dataDeletion],
  ] as const;

  return (
    <div className="flex min-h-dvh flex-col bg-surface">
      <SiteHeader />
      <main className="container-site flex-1 py-12 lg:py-16">
        <div className="mx-auto max-w-3xl">
          <nav aria-label={t.landing.footer.legal} className="flex flex-wrap gap-2">
            {links.map(([to, label]) => (
              <Link
                key={to}
                to={to}
                aria-current={pathname === to ? "page" : undefined}
                className={cx(
                  "rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors",
                  pathname === to ? "bg-brand-50 text-brand-700" : "text-slate-500 hover:bg-slate-100 hover:text-ink-950",
                )}
              >
                {label}
              </Link>
            ))}
          </nav>
          <h1 className="mt-10 text-3xl font-extrabold text-ink-950 sm:text-4xl">{page.title[lang]}</h1>
          <p className="mt-3 text-sm text-slate-400">
            {t.legal.lastUpdated}: {f.date(UPDATED)}
          </p>
          <article className="legal mt-10 space-y-4 text-[15px] leading-8 text-slate-700 [&_a]:font-medium [&_a]:text-brand-700 [&_a]:underline [&_a]:underline-offset-2 [&_h2]:mt-10 [&_h2]:scroll-mt-24 [&_h2]:text-lg [&_h2]:font-bold [&_h2]:text-ink-950 [&_h3]:mt-6 [&_h3]:font-bold [&_h3]:text-ink-900 [&_li]:ms-5 [&_ol]:list-decimal [&_ol]:space-y-1 [&_ul]:list-disc [&_ul]:space-y-1">
            {page.body[lang]}
          </article>
          {loggedIn && (
            <Link to="/" className="mt-12 inline-block text-sm font-semibold text-brand-700 hover:underline">
              {t.legal.backToPanel}
            </Link>
          )}
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}

const mail = <a href={`mailto:${SUPPORT_EMAIL}`} dir="ltr">{SUPPORT_EMAIL}</a>;

// ---------------------------------------------------------------------------- privacy

const privacy: Page = {
  title: { ar: "سياسة الخصوصية", en: "Privacy Policy" },
  body: {
    ar: (
      <>
        <p>
          يساعد Replisto (ويُشار إليه في هذه الوثيقة بـ«نحن» أو «الخدمة») المتاجر والأعمال الإلكترونية على تمكين مساعد ذكاء اصطناعي من الرد على رسائل عملائها المباشرة على
          <b> إنستغرام</b>، باستخدام المعلومات والمنتجات التي يقدّمها المتجر نفسه. توضّح هذه الوثيقة البيانات التي نعالجها ولماذا وكيف؛ سواء لأصحاب المتاجر الذين
          يستخدمون Replisto أو للعملاء الذين يراسلون تلك المتاجر.
        </p>
        <p>
          يُشغَّل Replisto من لبنان، ونعالج البيانات الشخصية وفقًا للقانون اللبناني، ولا سيما <b>القانون رقم 81 تاريخ 10 تشرين الأول 2018</b> المتعلق بالمعاملات
          الإلكترونية والبيانات ذات الطابع الشخصي.
        </p>

        <h2>1. بيانات صاحب المتجر</h2>
        <ul>
          <li>
            <b>الحساب:</b> البريد الإلكتروني والاسم واسم المتجر وكلمة المرور. تُخزَّن كلمة المرور كتجزئة أحادية الاتجاه فقط.
          </li>
          <li>
            <b>التحقق:</b> حالة تأكيد البريد الإلكتروني، ورقم الجوال الذي تؤكده برسالة SMS. تُخزَّن رموز SMS كتجزئة فقط ولبضع دقائق.
          </li>
          <li>
            <b>معلومات المتجر ومنتجاته:</b> النصوص والملفات والصور والروابط التي تضيفها في اللوحة، وقوائم المنتجات (يدويًا أو من ملفات أو من Google Sheets)، والرسائل
            التي تكتبها لتعليم البوت.
          </li>
          <li>
            <b>المحفظة والمدفوعات:</b> الرصيد وسجل الشحن والاستخدام، ولكل دفعة مبلغها وحالتها وطريقتها. يتم الشحن بتحويل عبر <b>Whish Money</b> أو <b>OMT</b>
            (نحفظ المبلغ ورقم التحويل الذي تُدخله)، أو بالبطاقة عبر <b>Stripe</b> حيث يتوفر ذلك (تُدخل بيانات بطاقتك في صفحة Stripe الآمنة مباشرة، ولا نستلمها أبدًا).
          </li>
          <li>
            <b>الاستخدام:</b> عدد ردود الذكاء الاصطناعي وحجمها (لحساب التكلفة).
          </li>
        </ul>

        <h2>2. بيانات عملاء المتاجر</h2>
        <p>عندما يربط متجر حسابه الاحترافي على إنستغرام عبر المسار الرسمي لـ Meta، ويراسله أحد العملاء، نخزّن:</p>
        <ul>
          <li>نص الرسائل المباشرة والردود التي أرسلها البوت أو المتجر. أما المرفقات (صور، صوت، ملفات…) فيُسجَّل نوعها فقط دون حفظ الملف.</li>
          <li>معرّف العميل على إنستغرام واسم المستخدم، لتصل المحادثة إلى المتجر الصحيح ويعرف صاحب المتجر مع من يتحدث.</li>
          <li>معرّف حساب المتجر واسم المستخدم ومنشوراته (لعرض المنتجات)، ورمز وصول صادر عن Meta يُخزَّن مشفّرًا.</li>
        </ul>
        <p>هذه البيانات ملك لذلك المتجر، ولا يراها إلا صاحبه في لوحته. ويتحمّل المتجر مسؤولية إعلام عملائه باستخدام مساعد ذكاء اصطناعي.</p>

        <h3>المحادثة مع مساعد Replisto على موقعنا</h3>
        <p>
          إذا تحدثت مع مساعد Replisto على موقعنا، نخزّن نص الرسائل ومعرّفًا عشوائيًا يحتفظ به متصفحك (وحسابك إن كنت مسجّل الدخول)، لتستمر المحادثة ويتمكن
          فريقنا من الرد على ما لا يعرفه المساعد. ولمنع إساءة الاستخدام نحسب الاستهلاك اليومي مع عنوان IP الخاص بك، ونحتفظ بهذه العدّادات 7 أيام كحد أقصى.
        </p>

        <h2>3. كيف نستخدمها</h2>
        <ul>
          <li>لإنشاء الردود وإرسالها إلى العملاء نيابة عن المتجر، ولتحويل المحادثة إلى صاحب المتجر عندما لا يعرف البوت الإجابة.</li>
          <li>لعرض المحادثات والمنتجات والتقارير في اللوحة، وإرسال الإشعارات إلى صاحب المتجر.</li>
          <li>لحساب التكاليف والخصم من المحفظة ومعالجة الشحن.</li>
          <li>لتأكيد البريد الإلكتروني وأرقام الجوال ومنع إساءة الاستخدام؛ مثل منح هدية البداية مرة واحدة لكل شخص، وتحديد عدد محاولات الدخول وطلبات الرموز.</li>
          <li>لإرسال الرسائل والبريد الذي تحتاجه الخدمة (التأكيد، استعادة كلمة المرور، انخفاض الرصيد). لا نرسل رسائل تسويقية دون إذنك.</li>
          <li>لاكتشاف الأخطاء التقنية وإصلاحها والحفاظ على أمان الخدمة.</li>
        </ul>
        <p>
          نحن <b>لا نبيع</b> البيانات، ولا نستخدمها <b>للإعلانات</b>، ولا نستخدمها <b>لتدريب نماذج الذكاء الاصطناعي</b>.
        </p>

        <h2>4. من يستلم البيانات</h2>
        <p>فقط ما يلزم لتشغيل الخدمة:</p>
        <ul>
          <li>
            <b>مزوّد الذكاء الاصطناعي:</b> رسالة العميل وبضع رسائل سابقة من المحادثة ومعلومات المتجر ومنتجاته ذات الصلة، فقط لإنشاء الرد.
          </li>
          <li>
            <b>Meta (إنستغرام):</b> تمرّ الرسائل بطبيعتها عبر إنستغرام، وتخضع أيضًا لشروط Meta وسياسة الخصوصية الخاصة بها.
          </li>
          <li>
            <b>Whish Money</b> و<b>OMT</b> و<b>Stripe</b> (لشحن المحفظة)، و<b>Twilio</b> (لرموز التحقق عبر SMS)، و<b>مزوّد البريد الإلكتروني</b> (لرسائل الخدمة)،
            و<b>مزوّد الاستضافة</b>.
          </li>
          <li>
            <b>مراقبة الأخطاء:</b> التفاصيل التقنية للأخطاء (مع تجنّب محتوى المحادثات قدر الإمكان).
          </li>
          <li>جهة مختصة، عندما يقتضي القانون ذلك.</li>
        </ul>
        <p>
          قد تقع خوادم Replisto وبعض هذه الخدمات خارج لبنان؛ وفي هذه الحالة لا تُنقل البيانات إلا بالقدر اللازم لتشغيل الخدمة ومع مزوّدين يلتزمون بحمايتها.
        </p>

        <h2>5. التخزين والأمان</h2>
        <ul>
          <li>جميع الاتصالات مع اللوحة والخادم مشفّرة (HTTPS).</li>
          <li>تُخزَّن كلمات المرور ورموز التحقق كتجزئة فقط، وتُخزَّن رموز الوصول مشفّرة.</li>
          <li>لا يصل كل متجر إلا إلى بياناته.</li>
          <li>تُنسخ قاعدة البيانات احتياطيًا بانتظام بشكل مشفّر؛ وتُحفظ النسخ 14 يومًا كحد أقصى ثم تُحذف.</li>
        </ul>

        <h2>6. مدة الاحتفاظ والحذف</h2>
        <p>
          تُحفظ البيانات طالما الحساب نشط. عند حذف الحساب، تُحذف جميع بياناته فورًا ونهائيًا — المحادثات وبيانات العملاء ومعلومات المتجر والمنتجات والربط والمحفظة
          وسجلها — وتختفي من النسخ الاحتياطية خلال 14 يومًا.
        </p>
        <p>
          استثناء واحد: حتى لا تُطلب هدية البداية مجددًا بحذف الحساب وإنشائه من جديد، نحتفظ ببصمة أحادية الاتجاه (تجزئة بمفتاح سري) لرقم الجوال الذي حصل عليها. لا يمكن
          استعادة الرقم منها، وتُستخدم لهذه المقارنة فقط.
        </p>
        <p>
          التعليمات الكاملة: <Link to="/data-deletion">حذف البيانات</Link>.
        </p>

        <h2>7. حقوقك</h2>
        <p>وفقًا للقانون رقم 81/2018، يحق لك الاطلاع على بياناتك الشخصية وتصحيحها والاعتراض على معالجتها وطلب حذفها:</p>
        <ul>
          <li>يمكنك عرض معلومات حسابك ومتجرك وتعديلها في اللوحة في أي وقت.</li>
          <li>يمكنك فصل حسابك على إنستغرام من اللوحة في أي وقت.</li>
          <li>يمكنك حذف حسابك وجميع بياناته في أي وقت.</li>
          <li>يمكن لعملاء المتاجر أن يطلبوا منا حذف محادثاتهم (انظر «حذف البيانات»).</li>
        </ul>

        <h2>8. السن</h2>
        <p>لوحة Replisto مخصّصة لأصحاب الأعمال؛ ولا يجوز لمن هم دون 18 عامًا إنشاء حساب.</p>

        <h2>9. التغييرات</h2>
        <p>إذا تغيّرت هذه السياسة، ننشر النسخة الجديدة هنا مع تاريخها ونعلن التغييرات المهمة في اللوحة أو عبر البريد الإلكتروني.</p>

        <h2>10. التواصل</h2>
        <p>للأسئلة أو الطلبات المتعلقة بالخصوصية: {mail}</p>
      </>
    ),
    en: (
      <>
        <p>
          Replisto (“we”, “the service”) helps online shops and businesses let an AI assistant answer their customers' <b>Instagram</b> direct messages, using the information
          and products the shop provides. This policy explains what data we process, why and how — both for shop owners who use Replisto and for the customers who message
          those shops.
        </p>
        <p>
          Replisto is operated from Lebanon. We process personal data in line with Lebanese law, in particular <b>Law No. 81 of 10 October 2018</b> on Electronic
          Transactions and Personal Data.
        </p>

        <h2>1. Shop owners' data</h2>
        <ul>
          <li>
            <b>Account:</b> email address, name, shop name and password. The password is stored only as a one-way hash.
          </li>
          <li>
            <b>Verification:</b> whether the email is verified, and the mobile number you verify by SMS. SMS codes are stored only as a hash, for a few minutes.
          </li>
          <li>
            <b>Shop information and products:</b> text, files, photos and links you add in the panel, product lists (manual, from files or Google Sheets), and the messages
            you write to teach the bot.
          </li>
          <li>
            <b>Wallet and payments:</b> balance, top-up and usage history, and for each payment its amount, status and method. Top-ups are made by{" "}
            <b>Whish Money</b> or <b>OMT</b> transfer (we keep the amount and the transfer reference you enter) or, where available, by card through <b>Stripe</b> (you
            enter your card details on Stripe's secure page directly, and we never receive them).
          </li>
          <li>
            <b>Usage:</b> the number and size of AI answers (to calculate costs).
          </li>
        </ul>

        <h2>2. Data about the shops' customers</h2>
        <p>When a shop connects its Instagram professional account through Meta's official flow and a customer messages it, we store:</p>
        <ul>
          <li>The text of the direct messages and of the replies sent by the bot or the shop. For attachments (photos, audio, files…) only the type is recorded, not the file.</li>
          <li>The customer's Instagram-scoped ID and username, so the conversation reaches the right shop and the owner knows who they're talking to.</li>
          <li>The shop account's ID and username, its posts (to show products), and an access token issued by Meta, which is stored encrypted.</li>
        </ul>
        <p>This data belongs to that shop and only that shop's owner sees it in their panel. The shop is responsible for letting its customers know an AI assistant is used.</p>

        <h3>Chatting with the Replisto assistant on our website</h3>
        <p>
          If you chat with the Replisto assistant on our website, the messages, a random ID your browser keeps (and your account, if you're logged in) are stored so the
          conversation can continue and our team can answer what the assistant doesn't know. To prevent abuse, daily usage is counted together with your IP address;
          these counters are kept for at most 7 days.
        </p>

        <h2>3. How we use it</h2>
        <ul>
          <li>To generate and send replies to customers on the shop's behalf, and to hand a conversation to the owner when the bot doesn't know the answer.</li>
          <li>To show conversations, products and reports in the panel, and to notify the owner.</li>
          <li>To calculate costs, charge the wallet and process top-ups.</li>
          <li>To verify emails and phone numbers and prevent abuse — for example giving the welcome gift only once per person, and limiting login attempts and code requests.</li>
          <li>To send emails and messages the service needs (verification, password reset, low balance). We don't send marketing without your permission.</li>
          <li>To find and fix technical errors and keep the service secure.</li>
        </ul>
        <p>
          We do <b>not sell</b> data, use it for <b>advertising</b>, or use it to <b>train AI models</b>.
        </p>

        <h2>4. Who receives data</h2>
        <p>Only what is needed to run the service:</p>
        <ul>
          <li>
            <b>The AI provider:</b> the customer's message, a few earlier messages of the conversation and the shop's relevant information and products, only to produce a reply.
          </li>
          <li>
            <b>Meta (Instagram):</b> messages travel through Instagram by nature and are also subject to Meta's own terms and privacy policy.
          </li>
          <li>
            <b>Whish Money</b>, <b>OMT</b> and <b>Stripe</b> (wallet top-ups), <b>Twilio</b> (SMS verification codes), an <b>email provider</b> (service emails) and
            our <b>hosting provider</b>.
          </li>
          <li>
            <b>Error monitoring:</b> technical details of errors (avoiding conversation content where possible).
          </li>
          <li>A competent authority, when the law requires it.</li>
        </ul>
        <p>
          Replisto's servers and some of these services may be located outside Lebanon. Data is then transferred only as far as running the service requires, and only to
          providers committed to protecting it.
        </p>

        <h2>5. Storage and security</h2>
        <ul>
          <li>All connections to the panel and server are encrypted (HTTPS).</li>
          <li>Passwords and verification codes are stored only as hashes; access tokens are encrypted.</li>
          <li>Each shop can access only its own data.</li>
          <li>The database is backed up regularly in encrypted form; backups are kept for at most 14 days and then deleted.</li>
        </ul>

        <h2>6. Retention and deletion</h2>
        <p>
          Data is kept while the account is active. When an account is deleted, all of its data — conversations and customer details, shop information, products,
          connections, the wallet and its history — is deleted immediately and permanently, and disappears from backups within 14 days.
        </p>
        <p>
          One exception: so the welcome gift can't be claimed again by deleting and re-creating an account, we keep a one-way fingerprint (a keyed hash) of the mobile number
          that received it. The number cannot be recovered from it; it is used only for that comparison.
        </p>
        <p>
          Full instructions: <Link to="/data-deletion?lang=en">Data Deletion</Link>.
        </p>

        <h2>7. Your rights</h2>
        <p>Under Law No. 81/2018 you have the right to access your personal data, correct it, object to its processing and ask for it to be deleted:</p>
        <ul>
          <li>You can see and edit your account and shop information in the panel at any time.</li>
          <li>You can disconnect your Instagram account from the panel at any time.</li>
          <li>You can delete your account and all its data at any time.</li>
          <li>Customers of shops can ask us to delete their conversation (see Data Deletion).</li>
        </ul>

        <h2>8. Age</h2>
        <p>The Replisto panel is for business owners; people under 18 should not create an account.</p>

        <h2>9. Changes</h2>
        <p>If this policy changes, we publish the new version here with its date and announce important changes in the panel or by email.</p>

        <h2>10. Contact</h2>
        <p>Privacy questions or requests: {mail}</p>
      </>
    ),
  },
};

// ---------------------------------------------------------------------------- terms

const terms: Page = {
  title: { ar: "شروط الاستخدام", en: "Terms of Service" },
  body: {
    ar: (
      <>
        <p>
          بإنشاء حساب في Replisto أو استخدامه، فإنك توافق على هذه الشروط وعلى <Link to="/privacy">سياسة الخصوصية</Link>. إذا لم توافق عليها، فلا تستخدم الخدمة.
        </p>

        <h2>1. الخدمة</h2>
        <p>
          Replisto مساعد ذكاء اصطناعي يرد على الرسائل المباشرة لعملائك على <b>إنستغرام</b> نيابة عن متجرك باستخدام المعلومات والمنتجات التي تقدّمها، ويحوّل إليك الأسئلة
          التي لا يعرف إجابتها، ويعرض المحادثات في لوحتك.
        </p>
        <p>يجيب Replisto عن الأسئلة فقط؛ فهو لا يستلم الطلبات أو المدفوعات وليس طرفًا في مبيعاتك.</p>

        <h2>2. حسابك</h2>
        <ul>
          <li>يجب أن تكون بيانات حسابك صحيحة وخاصة بك. وأنت مسؤول عن كلمة مرورك وعن أمان حساب إنستغرام الذي تربطه.</li>
          <li>قد نطلب منك تأكيد بريدك الإلكتروني ورقم جوالك.</li>
          <li>لا يمكن تأكيد رقم الجوال إلا على حساب واحد.</li>
        </ul>

        <h2>3. مسؤولياتك</h2>
        <ul>
          <li>يجب أن تكون مالكًا للحسابات التي تربطها أو مخوّلًا بإدارتها، وأن تلتزم بشروط إنستغرام وMeta.</li>
          <li>أنت مسؤول عن دقة معلومات متجرك وأسعارك ومخزونك وشروط البيع. جرّب البوت في صفحة الاختبار قبل تشغيله، وراجع ردوده من حين لآخر.</li>
          <li>يُحظر بيع السلع أو الخدمات غير القانونية، والاحتيال، والرسائل الجماعية أو غير المرغوب فيها (السبام)، وأي استخدام غير قانوني أو مسيء لـ Replisto.</li>
          <li>أعلِم عملاءك بأن مساعد ذكاء اصطناعي يرد عليهم، وتعامل مع بياناتهم وفق القانون.</li>
        </ul>

        <h2>4. الردود المولّدة بالذكاء الاصطناعي</h2>
        <p>
          تُنشأ الردود تلقائيًا، ورغم جهودنا قد تكون أحيانًا ناقصة أو خاطئة. يستخدم Replisto معلوماتك فقط؛ وعندما لا يعرف إجابة يرسل رسالتك المختارة ويحوّل المحادثة
          إليك. يمكنك إيقاف البوت لأي عميل أو إيقافه تمامًا في أي وقت. والتزامات المتجر تجاه عملائه مسؤولية المتجر نفسه.
        </p>

        <h2 id="wallet">5. المحفظة والرسوم</h2>
        <ul>
          <li>Replisto مدفوع مسبقًا: تشحن محفظة متجرك بالدولار الأمريكي ويُخصم منها كل رد للبوت حسب الاستخدام، مع حد أدنى لكل رد. الأسعار الحالية في صفحة «المحفظة» في اللوحة.</li>
          <li>
            يتم الشحن بتحويل عبر Whish Money أو OMT إلى الحساب المعروض في اللوحة، أو بالبطاقة عبر Stripe حيث يتوفر ذلك. يُضاف التحويل إلى المحفظة بعد أن نتأكد من
            وصوله؛ أرسل المبلغ نفسه المعروض وأدخل رقم التحويل الصحيح. وتتحمّل أنت أي رسوم يفرضها مزوّد التحويل.
          </li>
          <li>عند نفاد الرصيد، يتوقف البوت عن الرد على العملاء وتُحوَّل الرسائل إليك حتى تشحن المحفظة.</li>
          <li>
            <b>رصيد المحفظة غير قابل للاسترداد:</b> لا يُحوَّل الشحن إلى نقد ولا يُعاد إلى البطاقة؛ ولا يُستخدم إلا لخدمات Replisto في الحساب نفسه، ولا يمكن نقله إلى
            حساب آخر. إذا خُصم منك مبلغ ولم تُشحن المحفظة، راسل الدعم لنتحقق منه.
          </li>
          <li>يسقط أي رصيد متبقٍّ عند حذف الحساب.</li>
          <li>
            <b>هدية البداية:</b> يُمنح رصيد الهدية مرة واحدة لكل شخص (بعد تأكيد رقم الجوال). ليست له قيمة نقدية، ويُزال إذا حُصل عليه عبر حسابات متعددة أو أي خداع آخر.
          </li>
          <li>قد نغيّر الأسعار؛ ونعلن التغييرات في اللوحة قبل 7 أيام على الأقل، ولا تؤثر على الاستخدام السابق.</li>
        </ul>

        <h2>6. التوفر</h2>
        <p>
          نعمل على إبقاء الخدمة متاحة لكننا لا نضمن عملها دون انقطاع. يعتمد Replisto على توفر إنستغرام ومزوّد الذكاء الاصطناعي وخدمات الدفع والإنترنت والكهرباء،
          وهي خارجة عن إرادتنا.
        </p>

        <h2>7. حدود المسؤولية</h2>
        <p>
          Replisto أداة للمساعدة في الرد على العملاء. لسنا مسؤولين عن الخسائر غير المباشرة أو فقدان المبيعات أو الأرباح أو عواقب الردود المبنية على معلومات المتجر. وفي
          جميع الأحوال، تقتصر مسؤوليتنا على المبلغ الذي دفعته مقابل الخدمة خلال الأشهر الثلاثة السابقة.
        </p>

        <h2>8. التعليق والإنهاء</h2>
        <p>
          يمكنك حذف حسابك في أي وقت من «الحساب ← حذف الحساب»؛ وتُحذف حينها جميع بياناتك. وإذا انتُهكت هذه الشروط، يحق لنا إيقاف البوت أو الحساب مؤقتًا أو نهائيًا،
          وإبلاغك بالسبب متى أمكن.
        </p>

        <h2>9. تغيير هذه الشروط</h2>
        <p>قد نحدّث هذه الشروط. تُنشر النسخة الجديدة هنا مع تاريخها، ونعلن التغييرات المهمة في اللوحة أو عبر البريد الإلكتروني. ويعني استمرارك في الاستخدام قبولك للنسخة الجديدة.</p>

        <h2>10. القانون الحاكم</h2>
        <p>
          تخضع هذه الشروط للقانون اللبناني. ونسعى لحل أي خلاف وديًا أولًا عبر فريق الدعم؛ وإذا تعذّر ذلك، تختص محاكم بيروت دون سواها بالنظر فيه.
        </p>

        <h2>11. التواصل</h2>
        <p>{mail}</p>
      </>
    ),
    en: (
      <>
        <p>
          By creating a Replisto account or using the service you agree to these terms and the <Link to="/privacy?lang=en">Privacy Policy</Link>. If you don't agree, don't use
          the service.
        </p>

        <h2>1. The service</h2>
        <p>
          Replisto is an AI assistant that answers your customers' <b>Instagram</b> direct messages on behalf of your shop using the information and products you provide,
          hands you the questions it can't answer, and shows conversations in your panel.
        </p>
        <p>Replisto only answers questions; it doesn't take orders or payments and is not a party to your sales.</p>

        <h2>2. Your account</h2>
        <ul>
          <li>Your account details must be accurate and your own. You are responsible for your password and for the security of the Instagram account you connect.</li>
          <li>We may ask you to verify your email and mobile number.</li>
          <li>Each mobile number can be verified on one account only.</li>
        </ul>

        <h2>3. Your responsibilities</h2>
        <ul>
          <li>You must own, or be authorized to manage, the accounts you connect, and comply with the terms of Instagram and Meta.</li>
          <li>You are responsible for the accuracy of your shop information, prices, stock and terms of sale. Try the bot on the test page before turning it on, and review its answers from time to time.</li>
          <li>Selling illegal goods or services, fraud, bulk or unsolicited messages (spam) and any unlawful or abusive use of Replisto are forbidden.</li>
          <li>Let your customers know an AI assistant answers them, and handle their data lawfully.</li>
        </ul>

        <h2>4. AI-generated replies</h2>
        <p>
          Replies are generated automatically and, despite our efforts, may occasionally be incomplete or wrong. Replisto uses only your information; when it doesn't know an
          answer it sends your chosen message and hands the conversation to you. You can pause the bot for any customer or turn it off at any time. Commitments a shop makes to
          its customers are the shop's responsibility.
        </p>

        <h2 id="wallet">5. Wallet and fees</h2>
        <ul>
          <li>Replisto is prepaid: you top up your shop's wallet in US dollars and each bot answer is deducted from it by usage, with a minimum per answer. Current rates are on the panel's “Wallet” page.</li>
          <li>
            You top up by Whish Money or OMT transfer to the account shown in the panel, or by card through Stripe where available. A transfer is credited once we have
            confirmed we received it; send exactly the amount shown and enter the correct transfer reference. Any fee the transfer provider charges is yours.
          </li>
          <li>When the balance runs out, the bot stops answering customers and messages are handed to you until you top up.</li>
          <li>
            <b>Wallet credit is non-refundable:</b> top-ups are not converted to cash or returned to your card; they can only be used for Replisto's services in the same
            account, and can't be transferred to another account. If you were charged and your wallet wasn't topped up, message support and we will check it.
          </li>
          <li>Any remaining balance is forfeited when the account is deleted.</li>
          <li>
            <b>Welcome gift:</b> gift credit is given once per person (after verifying a mobile number). It has no cash value and is removed if obtained through multiple
            accounts or any other deception.
          </li>
          <li>We may change rates; we announce changes in the panel at least 7 days in advance, and they don't affect past usage.</li>
        </ul>

        <h2>6. Availability</h2>
        <p>
          We work to keep the service available but don't guarantee uninterrupted operation. Replisto depends on Instagram, the AI provider, the payment providers, the
          internet and electricity being available, which are beyond our control.
        </p>

        <h2>7. Limitation of liability</h2>
        <p>
          Replisto is a tool to help answer customers. We are not liable for indirect losses, lost sales or profits, or the consequences of replies generated from a shop's
          information. In any case our liability is limited to the amount you paid for the service in the previous three months.
        </p>

        <h2>8. Suspension and termination</h2>
        <p>
          You can delete your account at any time from Account → Delete account; all your data is then deleted. If these terms are violated, we may suspend the bot or the
          account temporarily or permanently, and tell you why where possible.
        </p>

        <h2>9. Changes to these terms</h2>
        <p>We may update these terms. The new version is published here with its date and important changes are announced in the panel or by email. Continuing to use the service means accepting the new version.</p>

        <h2>10. Governing law</h2>
        <p>
          These terms are governed by the laws of Lebanon. We aim to resolve any dispute amicably through our support first; failing that, the courts of Beirut have
          exclusive jurisdiction.
        </p>

        <h2>11. Contact</h2>
        <p>{mail}</p>
      </>
    ),
  },
};

// ---------------------------------------------------------------------------- data deletion

const dataDeletion: Page = {
  title: { ar: "تعليمات حذف البيانات", en: "Data Deletion Instructions" },
  body: {
    ar: (
      <>
        <h2>أصحاب المتاجر</h2>
        <p>لحذف حسابك وجميع البيانات المرتبطة به:</p>
        <ol>
          <li>سجّل الدخول إلى اللوحة.</li>
          <li>اذهب إلى <b>الحساب</b>.</li>
          <li>اضغط <b>حذف الحساب</b>، وأكّد، ثم أدخل كلمة المرور.</li>
        </ol>
        <p>
          الحذف فوري ونهائي: تُزال المحادثات وبيانات العملاء ومعلومات المتجر والمنتجات وربط إنستغرام والمحفظة وسجلها، وتختفي من النسخ الاحتياطية خلال 14 يومًا. أي رصيد
          متبقٍّ في المحفظة غير قابل للاسترداد. ويمكنك أيضًا مراسلة {mail} من البريد الإلكتروني لحسابك وسنحذف الحساب خلال 30 يومًا.
        </p>
        <p>
          الشيء الوحيد الذي يُحتفظ به هو بصمة أحادية الاتجاه للرقم الذي حصل على هدية البداية، حتى لا تُمنح مجددًا (انظر <Link to="/privacy">سياسة الخصوصية</Link>).
        </p>

        <h2>فصل إنستغرام دون حذف الحساب</h2>
        <ul>
          <li>في اللوحة، في صفحة إنستغرام، اضغط «فصل الربط».</li>
          <li>أو من إنستغرام: Settings ← Security ← Apps and websites ← إزالة التطبيق. يتوقف البوت حينها؛ ولحذف البيانات المخزّنة اتبع الخطوات أعلاه.</li>
        </ul>

        <h2>عملاء المتاجر</h2>
        <p>
          إذا راسلت متجرًا يستخدم Replisto على إنستغرام وتريد حذف رسائلك، أرسل إلى {mail} اسم المستخدم الخاص بك على إنستغرام واسم المتجر، وسنحذف محادثتك مع ذلك المتجر
          خلال 30 يومًا.
        </p>
      </>
    ),
    en: (
      <>
        <h2>Shop owners</h2>
        <p>To delete your account and all data associated with it:</p>
        <ol>
          <li>Log in to the panel.</li>
          <li>Go to <b>Account</b>.</li>
          <li>Click <b>Delete account</b>, confirm, and enter your password.</li>
        </ol>
        <p>
          Deletion is immediate and permanent: conversations and customer details, shop information, products, the Instagram connection, and the wallet with its history are
          removed, and disappear from backups within 14 days. Any remaining wallet balance is not refundable. You can also email {mail} from your account's email address
          and we will delete the account within 30 days.
        </p>
        <p>
          The only thing kept is a one-way fingerprint of the number that received the welcome gift, so it isn't given again (see the{" "}
          <Link to="/privacy?lang=en">Privacy Policy</Link>).
        </p>

        <h2>Disconnecting Instagram without deleting the account</h2>
        <ul>
          <li>In the panel, on the Instagram page, click “Disconnect”.</li>
          <li>
            Or from Instagram: Settings → Security → Apps and websites → remove the app. The bot then stops working; to delete stored data follow the steps above.
          </li>
        </ul>

        <h2>Customers of a shop</h2>
        <p>
          If you messaged a shop that uses Replisto on Instagram and want your messages deleted, email {mail} with your Instagram username and the shop's name. We will delete
          your conversation with that shop within 30 days.
        </p>
      </>
    ),
  },
};

export const Privacy = () => <LegalShell page={privacy} />;
export const Terms = () => <LegalShell page={terms} />;
export const DataDeletion = () => <LegalShell page={dataDeletion} />;
