import { useEffect, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { useAuth } from "../../auth/AuthContext";
import SiteFooter from "../../components/site/SiteFooter";
import SiteHeader from "../../components/site/SiteHeader";
import { cx } from "../../components/ui";
import { useI18n, type Lang } from "../../i18n";

// Public legal pages (no login): for owners and their customers, for the payment gateway's
// review, and later for Meta's app review. Every page has full English and Arabic versions;
// `?lang=en` / `?lang=ar` opens one directly. Every statement here must match what the
// product actually does: change the page when the product changes.

const SUPPORT_EMAIL = import.meta.env.VITE_SUPPORT_EMAIL || "support@replisto.app";
const UPDATED = "2026-10-04";

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
          يساعد Replisto (ويُشار إليه في هذه الوثيقة بـ«نحن» أو «الخدمة») المتاجر والأعمال الإلكترونية على تمكين مساعد ذكاء اصطناعي من الرد على رسائل عملائها، باستخدام
          المعلومات والمنتجات التي يقدّمها المتجر نفسه. يعمل Replisto اليوم على تطبيقَي المراسلة <b>تيليجرام</b> و<b>بله</b>، و<b>إنستغرام</b> قادم قريبًا. توضّح هذه
          الوثيقة البيانات التي نعالجها ولماذا وكيف؛ سواء لأصحاب المتاجر الذين يستخدمون Replisto أو للعملاء الذين يراسلون تلك المتاجر.
        </p>

        <h2>1. بيانات صاحب المتجر</h2>
        <ul>
          <li>
            <b>الحساب:</b> البريد الإلكتروني والاسم واسم المتجر وكلمة المرور. تُخزَّن كلمة المرور كتجزئة أحادية الاتجاه فقط.
          </li>
          <li>
            <b>التحقق:</b> حالة تأكيد البريد الإلكتروني، ورقم الجوال الذي تؤكده (برسالة SMS أو بمشاركة رقم حسابك على تيليجرام أو بله مع البوت). تُخزَّن رموز SMS كتجزئة
            فقط ولبضع دقائق.
          </li>
          <li>
            <b>حساب تيليجرام أو بله الذي تربطه بالمتجر:</b> معرّفه الرقمي واسم المستخدم والاسم المعروض، لنبلغك بالعملاء المنتظرين ولتتمكن من إدارة المتجر من داخل تطبيق
            المراسلة.
          </li>
          <li>
            <b>معلومات المتجر ومنتجاته:</b> النصوص والملفات والصور والروابط التي تضيفها في اللوحة أو ترسلها إلى البوت، وقوائم المنتجات (يدويًا أو من ملفات أو من Google
            Sheets)، ومنشورات قنوات تيليجرام التي جعلت البوت مشرفًا عليها، والرسائل التي تكتبها لتعليم البوت.
          </li>
          <li>
            <b>الربط:</b> رمز بوت تيليجرام أو بله الخاص بك (إن ربطته) ومعرّف ربط Telegram Business. تُخزَّن الرموز مشفّرة.
          </li>
          <li>
            <b>المحفظة والمدفوعات:</b> الرصيد والخطة وسجل الشحن والاستخدام، ولكل دفعة مبلغها وحالتها ورقم فاتورة البوابة. يتم الشحن عبر خدمة التحويل من بطاقة إلى بطاقة
            «Aban Gateway»: تحوّل المبلغ من تطبيقك البنكي إلى البطاقة المعروضة ويُؤكَّد الدفع تلقائيًا. لا نستلم أبدًا بيانات بطاقتك أو كلمات مرورك البنكية.
          </li>
          <li>
            <b>الاستخدام:</b> عدد ردود الذكاء الاصطناعي وحجمها (لحساب التكلفة).
          </li>
        </ul>

        <h2>2. بيانات عملاء المتاجر</h2>
        <p>عندما يراسل شخص ما بوت Replisto أو البوت الخاص بمتجر على تيليجرام أو بله، نخزّن:</p>
        <ul>
          <li>نص رسائله والردود التي أرسلها إليه البوت أو المتجر. أما المرفقات (صور، صوت، ملفات…) فيُسجَّل نوعها فقط دون حفظ الملف.</li>
          <li>معرّفه الرقمي واسم المستخدم والاسم المعروض في ذلك التطبيق، لتصل المحادثة إلى المتجر الصحيح ويعرف صاحب المتجر مع من يتحدث.</li>
          <li>
            إذا ربط المتجر ميزة «الرد من الحساب الشخصي» (Telegram Business): الرسائل الخاصة التي يرسلها العملاء إلى حساب صاحب المتجر على تيليجرام، والرسائل التي يرسلها
            صاحب المتجر في تلك المحادثات.
          </li>
        </ul>
        <p>هذه البيانات ملك لذلك المتجر، ولا يراها إلا صاحبه في لوحته. ويتحمّل المتجر مسؤولية إعلام عملائه باستخدام مساعد ذكاء اصطناعي.</p>

        <h3>إنستغرام (بعد تفعيله)</h3>
        <p>
          عند تفعيل إنستغرام وربط متجر لحسابه الاحترافي عبر المسار الرسمي لـ Meta، نستلم أيضًا: الرسائل المباشرة لذلك الحساب والردود عليها (النص ونوع المرفق)، ومعرّفات
          العملاء على إنستغرام وأسماء مستخدميهم، ومعرّف الحساب واسم المستخدم، ومنشوراته (لعرض المنتجات)، ورمز وصول صادر عن Meta يُخزَّن مشفّرًا.
        </p>

        <h2>3. كيف نستخدمها</h2>
        <ul>
          <li>لإنشاء الردود وإرسالها إلى العملاء نيابة عن المتجر، ولتحويل المحادثة إلى صاحب المتجر عندما لا يعرف البوت الإجابة.</li>
          <li>لعرض المحادثات والمنتجات والتقارير في اللوحة، وإرسال الإشعارات إلى تيليجرام أو بله الخاص بصاحب المتجر.</li>
          <li>لحساب التكاليف والخصم من المحفظة ومعالجة الشحن وتجديد الخطط.</li>
          <li>لتأكيد البريد الإلكتروني وأرقام الجوال ومنع إساءة الاستخدام؛ مثل منح هدية البداية مرة واحدة لكل شخص، وتحديد عدد محاولات الدخول وطلبات الرموز.</li>
          <li>لإرسال الرسائل والبريد الذي تحتاجه الخدمة (التأكيد، استعادة كلمة المرور، انخفاض الرصيد، تغيير الخطة). لا نرسل رسائل تسويقية دون إذنك.</li>
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
            <b>تيليجرام وبله:</b> تمرّ الرسائل بطبيعتها عبر هذين التطبيقين، وتخضع أيضًا لشروطهما وسياسات الخصوصية الخاصة بهما.
          </li>
          <li>
            خدمة الدفع <b>Aban Gateway</b> (لشحن المحفظة)، و<b>مزوّد خدمة SMS</b> (لرموز التحقق)، و<b>مزوّد البريد الإلكتروني</b> (لرسائل الخدمة)، و<b>مزوّد الاستضافة</b>.
          </li>
          <li>
            <b>مراقبة الأخطاء:</b> التفاصيل التقنية للأخطاء (مع تجنّب محتوى المحادثات قدر الإمكان).
          </li>
          <li>جهة مختصة، عندما يقتضي القانون ذلك.</li>
        </ul>
        <p>قد تقع خوادم Replisto وبعض هذه الخدمات خارج إيران.</p>

        <h2>5. التخزين والأمان</h2>
        <ul>
          <li>جميع الاتصالات مع اللوحة والخادم مشفّرة (HTTPS).</li>
          <li>تُخزَّن كلمات المرور ورموز التحقق كتجزئة فقط، وتُخزَّن رموز البوتات والربط مشفّرة.</li>
          <li>لا يصل كل متجر إلا إلى بياناته.</li>
          <li>تُنسخ قاعدة البيانات احتياطيًا بانتظام بشكل مشفّر؛ وتُحفظ النسخ 14 يومًا كحد أقصى ثم تُحذف.</li>
        </ul>

        <h2>6. مدة الاحتفاظ والحذف</h2>
        <p>
          تُحفظ البيانات طالما الحساب نشط. عند حذف الحساب، تُحذف جميع بياناته فورًا ونهائيًا — المحادثات وبيانات العملاء ومعلومات المتجر والمنتجات والربط والمحفظة
          وسجلها — وتختفي من النسخ الاحتياطية خلال 14 يومًا.
        </p>
        <p>
          استثناء واحد: حتى لا تُطلب هدية البداية مجددًا بحذف الحساب وإنشائه من جديد، نحتفظ ببصمة أحادية الاتجاه (تجزئة بمفتاح سري) لمعرّف حساب تيليجرام أو بله ورقم
          الجوال الذي حصل عليها. لا يمكن استعادة الرقم أو المعرّف منها، وتُستخدم لهذه المقارنة فقط.
        </p>
        <p>
          التعليمات الكاملة: <Link to="/data-deletion">حذف البيانات</Link>.
        </p>

        <h2>7. حقوقك</h2>
        <ul>
          <li>يمكنك عرض معلومات حسابك ومتجرك وتعديلها في اللوحة في أي وقت.</li>
          <li>يمكنك فصل حسابك على تيليجرام أو بله وبوتك الخاص وقناتك من اللوحة في أي وقت.</li>
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
          Replisto (“we”, “the service”) helps online shops and businesses let an AI assistant answer their customers' messages, using the information and products the
          shop provides. Today Replisto works on the <b>Telegram</b> and <b>Bale</b> messengers; <b>Instagram</b> is coming soon. This policy explains what data we process,
          why and how — both for shop owners who use Replisto and for the customers who message those shops.
        </p>

        <h2>1. Shop owners' data</h2>
        <ul>
          <li>
            <b>Account:</b> email address, name, shop name and password. The password is stored only as a one-way hash.
          </li>
          <li>
            <b>Verification:</b> whether the email is verified, and the mobile number you verify (by SMS, or by sharing your Telegram or Bale account's number with our bot).
            SMS codes are stored only as a hash, for a few minutes.
          </li>
          <li>
            <b>The Telegram or Bale account you link to the shop:</b> its numeric ID, username and display name, so we can tell you about waiting customers and you can manage
            the shop from the messenger.
          </li>
          <li>
            <b>Shop information and products:</b> text, files, photos and links you add in the panel or send the bot, product lists (manual, from files or Google Sheets),
            posts of Telegram channels where you made the bot an admin, and the messages you write to teach the bot.
          </li>
          <li>
            <b>Connections:</b> the token of your own Telegram or Bale bot (if you connect one) and the Telegram Business connection ID. Tokens are stored encrypted.
          </li>
          <li>
            <b>Wallet and payments:</b> balance, plan, top-up and usage history, and for each payment its amount, status and the gateway's invoice ID. Top-ups go through
            the Aban Gateway card-to-card service: you transfer from your own banking app to the card shown and the payment is confirmed automatically. We never receive
            your card details or banking passwords.
          </li>
          <li>
            <b>Usage:</b> the number and size of AI answers (to calculate costs).
          </li>
        </ul>

        <h2>2. Data about the shops' customers</h2>
        <p>When someone messages the Replisto bot or a shop's own bot on Telegram or Bale, we store:</p>
        <ul>
          <li>The text of their messages and of the replies sent to them by the bot or the shop. For attachments (photos, audio, files…) only the type is recorded, not the file.</li>
          <li>Their numeric ID, username and display name on that messenger, so the conversation reaches the right shop and the owner knows who they're talking to.</li>
          <li>
            If the shop connected “answer from my personal account” (Telegram Business): the private messages customers send to the owner's Telegram account, and the messages
            the owner sends in those chats.
          </li>
        </ul>
        <p>This data belongs to that shop and only that shop's owner sees it in their panel. The shop is responsible for letting its customers know an AI assistant is used.</p>

        <h3>Instagram (once enabled)</h3>
        <p>
          When Instagram is enabled and a shop connects its professional account through Meta's official flow, we also receive: Direct Messages to that account and the replies
          (text and attachment type), customers' Instagram-scoped IDs and usernames, the account's ID and username, its posts (to show products), and an access token issued by
          Meta, which is stored encrypted.
        </p>

        <h2>3. How we use it</h2>
        <ul>
          <li>To generate and send replies to customers on the shop's behalf, and to hand a conversation to the owner when the bot doesn't know the answer.</li>
          <li>To show conversations, products and reports in the panel, and to send notifications to the owner's Telegram or Bale.</li>
          <li>To calculate costs, charge the wallet, process top-ups and renew plans.</li>
          <li>To verify emails and phone numbers and prevent abuse — for example giving the welcome gift only once per person, and limiting login attempts and code requests.</li>
          <li>To send emails and messages the service needs (verification, password reset, low balance, plan changes). We don't send marketing without your permission.</li>
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
            <b>Telegram and Bale:</b> messages travel through these messengers by nature and are also subject to their own terms and privacy policies.
          </li>
          <li>
            The <b>Aban Gateway</b> payment service (wallet top-ups), an <b>SMS provider</b> (verification codes), an <b>email provider</b> (service emails) and our <b>hosting provider</b>.
          </li>
          <li>
            <b>Error monitoring:</b> technical details of errors (avoiding conversation content where possible).
          </li>
          <li>A competent authority, when the law requires it.</li>
        </ul>
        <p>Replisto's servers and some of these services may be located outside Iran.</p>

        <h2>5. Storage and security</h2>
        <ul>
          <li>All connections to the panel and server are encrypted (HTTPS).</li>
          <li>Passwords and verification codes are stored only as hashes; bot tokens and connection tokens are encrypted.</li>
          <li>Each shop can access only its own data.</li>
          <li>The database is backed up regularly in encrypted form; backups are kept for at most 14 days and then deleted.</li>
        </ul>

        <h2>6. Retention and deletion</h2>
        <p>
          Data is kept while the account is active. When an account is deleted, all of its data — conversations and customer details, shop information, products,
          connections, the wallet and its history — is deleted immediately and permanently, and disappears from backups within 14 days.
        </p>
        <p>
          One exception: so the welcome gift can't be claimed again by deleting and re-creating an account, we keep a one-way fingerprint (a keyed hash) of the Telegram or
          Bale account ID and the mobile number that received it. The number or ID cannot be recovered from it; it is used only for that comparison.
        </p>
        <p>
          Full instructions: <Link to="/data-deletion?lang=en">Data Deletion</Link>.
        </p>

        <h2>7. Your rights</h2>
        <ul>
          <li>You can see and edit your account and shop information in the panel at any time.</li>
          <li>You can disconnect your Telegram or Bale account, your own bot and your channel from the panel at any time.</li>
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
          Replisto مساعد ذكاء اصطناعي يرد على رسائل عملائك نيابة عن متجرك باستخدام المعلومات والمنتجات التي تقدّمها، ويحوّل إليك الأسئلة التي لا يعرف إجابتها، ويعرض
          المحادثات في لوحتك. يعمل اليوم على <b>تيليجرام</b> و<b>بله</b>: عبر رابط متجرك على بوت Replisto، أو بوتك الخاص، أو (على تيليجرام) نيابة عن حسابك الشخصي.
          وسيُضاف <b>إنستغرام</b> بعد موافقة Meta.
        </p>
        <p>يجيب Replisto عن الأسئلة فقط؛ فهو لا يستلم الطلبات أو المدفوعات وليس طرفًا في مبيعاتك.</p>

        <h2>2. حسابك</h2>
        <ul>
          <li>يجب أن تكون بيانات حسابك صحيحة وخاصة بك. وأنت مسؤول عن كلمة مرورك وعن أمان حسابات تيليجرام وبله التي تربطها.</li>
          <li>قد نطلب منك تأكيد بريدك الإلكتروني ورقم جوالك.</li>
          <li>يُربط كل حساب تيليجرام أو بله بمتجر واحد في كل مرة، ولا يمكن تأكيد رقم الجوال إلا على حساب واحد.</li>
        </ul>

        <h2>3. مسؤولياتك</h2>
        <ul>
          <li>يجب أن تكون مالكًا للقنوات والبوتات والحسابات التي تربطها أو مخوّلًا بإدارتها، وأن تلتزم بشروط تيليجرام وبله و(لاحقًا) إنستغرام وMeta.</li>
          <li>أنت مسؤول عن دقة معلومات متجرك وأسعارك ومخزونك وشروط البيع. جرّب البوت في صفحة الاختبار قبل تشغيله، وراجع ردوده من حين لآخر.</li>
          <li>يُحظر بيع السلع أو الخدمات غير القانونية، والاحتيال، والرسائل الجماعية أو غير المرغوب فيها (السبام)، وأي استخدام غير قانوني أو مسيء لـ Replisto.</li>
          <li>أعلِم عملاءك بأن مساعد ذكاء اصطناعي يرد عليهم، وتعامل مع بياناتهم وفق القانون.</li>
        </ul>

        <h2>4. الردود المولّدة بالذكاء الاصطناعي</h2>
        <p>
          تُنشأ الردود تلقائيًا، ورغم جهودنا قد تكون أحيانًا ناقصة أو خاطئة. يستخدم Replisto معلوماتك فقط؛ وعندما لا يعرف إجابة يرسل رسالتك المختارة ويحوّل المحادثة
          إليك. يمكنك إيقاف البوت لأي عميل أو إيقافه تمامًا في أي وقت. والتزامات المتجر تجاه عملائه مسؤولية المتجر نفسه.
        </p>

        <h2 id="wallet">5. المحفظة والرسوم والخطط</h2>
        <ul>
          <li>Replisto مدفوع مسبقًا: تشحن محفظة متجرك بالتومان ويُخصم منها كل رد للبوت حسب الاستخدام، مع حد أدنى لكل رد. الأسعار الحالية في صفحة «المحفظة والخطة» في اللوحة.</li>
          <li>للخطط الأعلى من «الأساسية» رسوم شهرية تُخصم من المحفظة وتتجدد كل 30 يومًا. ويسري الانتقال إلى خطة أدنى عند انتهاء الشهر المدفوع. وإذا لم يكفِ الرصيد للتجديد، تعود الخطة إلى «الأساسية».</li>
          <li>عند نفاد الرصيد، يتوقف البوت عن الرد على العملاء وتُحوَّل الرسائل إليك حتى تشحن المحفظة.</li>
          <li>
            <b>رصيد المحفظة غير قابل للاسترداد:</b> لا يُحوَّل الشحن إلى نقد ولا يُعاد إلى حساب بنكي؛ ولا يُستخدم إلا لخدمات Replisto في الحساب نفسه، ولا يمكن نقله إلى
            حساب آخر.
          </li>
          <li>
            يُؤكَّد الشحن بالتحويل من بطاقة إلى بطاقة تلقائيًا فقط عند تحويل <b>المبلغ نفسه تمامًا</b> المعروض في صفحة الدفع قبل انتهاء مهلته. إذا حوّلت مبلغًا مختلفًا أو
            تأخرت، راسل الدعم مع إيصال التحويل لنتحقق منه ونضيفه يدويًا.
          </li>
          <li>يسقط أي رصيد متبقٍّ عند حذف الحساب.</li>
          <li>
            <b>هدية البداية:</b> يُمنح رصيد الهدية مرة واحدة لكل شخص (بعد ربط حساب تيليجرام أو بله وتأكيد رقم الجوال). ليست له قيمة نقدية، ويُزال إذا حُصل عليه عبر حسابات
            متعددة أو أي خداع آخر.
          </li>
          <li>قد نغيّر الأسعار ورسوم الخطط؛ ونعلن التغييرات في اللوحة قبل 7 أيام على الأقل، ولا تؤثر على الاستخدام السابق.</li>
        </ul>

        <h2>6. التوفر</h2>
        <p>
          نعمل على إبقاء الخدمة متاحة لكننا لا نضمن عملها دون انقطاع. يعتمد Replisto على توفر تيليجرام وبله وإنستغرام ومزوّد الذكاء الاصطناعي وبوابة الدفع والإنترنت،
          بما في ذلك قيود الوصول إلى تيليجرام في إيران، وهي خارجة عن إرادتنا.
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
        <p>تخضع هذه الشروط لقوانين جمهورية إيران الإسلامية. ونسعى لحل أي خلاف أولًا عبر فريق الدعم.</p>

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
          Replisto is an AI assistant that answers your customers' messages on behalf of your shop using the information and products you provide, hands you the questions it
          can't answer, and shows conversations in your panel. Today it works on <b>Telegram</b> and <b>Bale</b>: through your shop's link on the Replisto bot, your own bot, or
          (on Telegram) on behalf of your personal account. <b>Instagram</b> will be added after Meta's approval.
        </p>
        <p>Replisto only answers questions; it doesn't take orders or payments and is not a party to your sales.</p>

        <h2>2. Your account</h2>
        <ul>
          <li>Your account details must be accurate and your own. You are responsible for your password and for the security of the Telegram and Bale accounts you link.</li>
          <li>We may ask you to verify your email and mobile number.</li>
          <li>Each Telegram or Bale account is linked to one shop at a time, and each mobile number can be verified on one account only.</li>
        </ul>

        <h2>3. Your responsibilities</h2>
        <ul>
          <li>You must own, or be authorized to manage, the channels, bots and accounts you connect, and comply with the terms of Telegram, Bale and (later) Instagram and Meta.</li>
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

        <h2 id="wallet">5. Wallet, fees and plans</h2>
        <ul>
          <li>Replisto is prepaid: you top up your shop's wallet in toman and each bot answer is deducted from it by usage, with a minimum per answer. Current rates are on the panel's “Wallet &amp; plan” page.</li>
          <li>Plans above “Basic” have a monthly fee, deducted from the wallet and renewed every 30 days. Moving to a lower plan takes effect when the paid month ends. If the balance can't cover a renewal, the plan returns to Basic.</li>
          <li>When the balance runs out, the bot stops answering customers and messages are handed to you until you top up.</li>
          <li>
            <b>Wallet credit is non-refundable:</b> top-ups are not converted to cash or returned to a bank account; they can only be used for Replisto's services in the same
            account, and can't be transferred to another account.
          </li>
          <li>
            A card-to-card top-up is confirmed automatically only when <b>exactly the amount</b> shown on the payment page is transferred before it expires. If you sent a
            different amount or sent it late, message support with the transfer receipt and we will check and credit it by hand.
          </li>
          <li>Any remaining balance is forfeited when the account is deleted.</li>
          <li>
            <b>Welcome gift:</b> gift credit is given once per person (after linking a Telegram or Bale account and verifying a mobile number). It has no cash value and is
            removed if obtained through multiple accounts or any other deception.
          </li>
          <li>We may change rates and plan fees; we announce changes in the panel at least 7 days in advance, and they don't affect past usage.</li>
        </ul>

        <h2>6. Availability</h2>
        <p>
          We work to keep the service available but don't guarantee uninterrupted operation. Replisto depends on Telegram, Bale, Instagram, the AI provider, the payment gateway
          and the internet being available, including access restrictions to Telegram in Iran, which are beyond our control.
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
        <p>These terms are governed by the laws of the Islamic Republic of Iran. We aim to resolve any dispute first through our support.</p>

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
          الحذف فوري ونهائي: تُزال المحادثات وبيانات العملاء ومعلومات المتجر والمنتجات وحسابات تيليجرام وبله المربوطة والبوتات الخاصة والقنوات والمحفظة وسجلها، وتختفي
          من النسخ الاحتياطية خلال 14 يومًا. أي رصيد متبقٍّ في المحفظة غير قابل للاسترداد. ويمكنك أيضًا مراسلة {mail} من البريد الإلكتروني لحسابك وسنحذف الحساب خلال 30
          يومًا.
        </p>
        <p>
          الشيء الوحيد الذي يُحتفظ به هو بصمة أحادية الاتجاه لمعرّف حساب تيليجرام أو بله والرقم الذي حصل على هدية البداية، حتى لا تُمنح مجددًا (انظر{" "}
          <Link to="/privacy">سياسة الخصوصية</Link>).
        </p>

        <h2>الفصل دون حذف الحساب</h2>
        <ul>
          <li>حسابك على تيليجرام أو بله: في اللوحة، في صفحة تيليجرام أو بله، اضغط «إزالة» بجانب الحساب.</li>
          <li>بوتك الخاص: اضغط «فصل الربط» في الصفحة نفسها.</li>
          <li>الرد من حسابك الشخصي (Telegram Business): احذف البوت من Chatbots في إعدادات تيليجرام، أو اضغط «إيقاف» في اللوحة.</li>
          <li>قناة تيليجرام: أزل البوت من مشرفي القناة.</li>
        </ul>

        <h2>إنستغرام (بعد تفعيله)</h2>
        <p>يمكنك إلغاء الوصول من إنستغرام: Settings ← Security ← Apps and websites ← إزالة التطبيق. يتوقف البوت حينها؛ ولحذف البيانات المخزّنة اتبع الخطوات أعلاه.</p>

        <h2>عملاء المتاجر</h2>
        <p>
          إذا راسلت متجرًا يستخدم Replisto على تيليجرام أو بله (أو إنستغرام) وتريد حذف رسائلك، أرسل إلى {mail} اسم المستخدم أو رقمك في ذلك التطبيق واسم المتجر، وسنحذف
          محادثتك مع ذلك المتجر خلال 30 يومًا. ولكي تتوقف عن تلقي الرسائل من البوت، يكفي حظره في التطبيق.
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
          Deletion is immediate and permanent: conversations and customer details, shop information, products, linked Telegram and Bale accounts, your own bots, channels,
          and the wallet with its history are removed, and disappear from backups within 14 days. Any remaining wallet balance is not refundable. You can also email {mail}{" "}
          from your account's email address and we will delete the account within 30 days.
        </p>
        <p>
          The only thing kept is a one-way fingerprint of the Telegram or Bale account ID and the number that received the welcome gift, so it isn't given again (see the{" "}
          <Link to="/privacy?lang=en">Privacy Policy</Link>).
        </p>

        <h2>Disconnecting without deleting the account</h2>
        <ul>
          <li>Your own Telegram or Bale account: in the panel, on the Telegram or Bale page, click “Remove” next to the account.</li>
          <li>Your own bot: click “Disconnect” on the same page.</li>
          <li>Answering from your personal account (Telegram Business): remove the bot under Chatbots in Telegram's settings, or click “Stop” in the panel.</li>
          <li>A Telegram channel: remove the bot from the channel's admins.</li>
        </ul>

        <h2>Instagram (once enabled)</h2>
        <p>
          You can revoke access from Instagram: Settings → Security → Apps and websites → remove the app. The bot then stops working; to delete stored data follow the steps
          above.
        </p>

        <h2>Customers of a shop</h2>
        <p>
          If you messaged a shop that uses Replisto on Telegram or Bale (or Instagram) and want your messages deleted, email {mail} with your username or number on that messenger
          and the shop's name. We will delete your conversation with that shop within 30 days. To stop receiving messages from the bot, simply block it in the messenger.
        </p>
      </>
    ),
  },
};

export const Privacy = () => <LegalShell page={privacy} />;
export const Terms = () => <LegalShell page={terms} />;
export const DataDeletion = () => <LegalShell page={dataDeletion} />;
