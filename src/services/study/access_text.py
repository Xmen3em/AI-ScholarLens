"""Student-facing copy for the multi-user beta, verbatim from docs/specs/multi-user.md §5."""

NOT_MEMBER = "البوت ده في تجربة محدودة بالدعوة. لو معاك كود دعوة ابعت: /start الكود"
BAD_CODE = "الكود ده مش صالح أو اتستخدم أو انتهى. اطلب كود جديد من صاحب البوت."
WELCOME = ("أهلًا بيك في تجربة ScholarLens! ابعت رابط ورقة من arXiv أو اسمها بالإنجليزي وهشرحهالك. "
           "اكتب /privacy تعرف إحنا بنحفظ إيه، و/usage تعرف فاضلك قد إيه النهارده.")
USAGE = "النهارده: فاضلك {p} من {P} ورقة و{q} من {Q} سؤال. العداد بيتصفّر الساعة 12 بالليل بتوقيت القاهرة."
PAPERS_USED = "خلّصت ورق النهارده ({P} من {P}). تقدر تكمّل أسئلة على الورقة الحالية، أو ترجع بكرة."
QUESTIONS_USED = "خلّصت أسئلة النهارده ({Q} من {Q}). ارجع بكرة."
CEILING = "البوت وصل لحد الاستخدام اليومي. ارجع بكرة، ومعلش على كده."
TOO_FAST = "استنى دقيقة قبل الرسالة الجاية."
QUEUED = "في الطابور: إنت رقم {n}. هبدأ أول ما ييجي دورك."
DEEP_OWNER_ONLY = "أمر /deep متاح لصاحب البوت بس في التجربة دي."
GROUP_CHAT = "البوت بيشتغل في الشات الخاص بس."
REVOKED = "العضوية دي اتلغت."
PRIVACY = ("بنحفظ الأوراق اللي فتحتها وأسئلتك وإجاباتها عشان نكمّل معاك. نص الورقة وسؤالك بيتبعتوا لموديل الذكاء "
           "الاصطناعي (GLM-5.3) عن طريق Hugging Face عشان يتعمل الشرح. لو ما استخدمتش البوت 30 يوم بنمسح كل ده "
           "تلقائيًا، و/forget بيمسحه فورًا. بنحتفظ بس بعدد الرسائل وتكلفتها من غير أي محتوى.")

STUDENT_HELP_LINES = (
    "/usage — فاضلك قد إيه النهارده",
    "/privacy — إحنا بنحفظ إيه",
    "/forget — امسح سياقك وتفضيلاتك",
)
OWNER_HELP_LINES = (
    "/invite أو /invite 5 — أكواد دعوة جديدة",
    "/members — الأعضاء واستخدامهم النهارده",
    "/revoke ID — إلغاء عضوية ومسح محتواها",
    "/usage — التكلفة النهارده والحد اليومي",
)

# Owner-facing replies (not in spec §5, which fixes the student copy).
INVITES = "أكواد الدعوة (كل كود لمرة واحدة، صالح 7 أيام):\n{codes}\n\nالطالب يبعت: /start الكود"
INVITE_HOW = "اكتب /invite أو /invite ورقم من 1 لـ 10."
REVOKE_HOW = "اكتب /revoke ورقم الطالب من /members."
REVOKE_DONE = "اتلغت عضوية {user} واتمسح محتواها. سجل الاستخدام بيفضل من غير محتوى."
NO_SUCH_MEMBER = "مفيش طالب نشط بالرقم ده."
MEMBER_LINE = "{user} — {role} — آخر نشاط {last_active} — النهارده: {papers} ورقة، {questions} سؤال، ${usd:.2f}"
OWNER_USAGE = "النهارده: اتصرف ${spent:.2f} ومحجوز ${reserved:.2f} من الحد اليومي ${ceiling:.2f}."
OWNER_TOP = "{user}: ${usd:.2f} — {papers} ورقة، {questions} سؤال"
# A student without a paper gets this instead of the owner's general-knowledge fallback.
NO_PAPER_YET = "لسه مفيش ورقة مفتوحة. ابعت رقم arXiv (زي 2005.11401) أو /paper واسم الورقة بالإنجليزي، وبعدها اسألني."
