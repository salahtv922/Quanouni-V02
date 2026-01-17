import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure API
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not found in .env")

genai.configure(api_key=api_key)

# List available models to find the correct name for "Gemini 3" or latest Pro
print("🔍 Listing available models...")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(f" - {m.name}")

# Newer models (3 Pro, 2.0 Flash) gave Quota Error (Limit 0).
# Trying the stable 'latest' alias which usually points to a model with valid free tier.
MODEL_NAME = "models/gemini-flash-latest" 

print(f"\n🚀 Initializing {MODEL_NAME} for Legal Pleading Test...")

# --- MOCK DATA (Simulating RAG Retrieval) ---
# In a real scenario, this comes from Supabase
mock_case_data = {
    "court": "محكمة الجنايات بالجزائر العاصمة",
    "defendant": "فاروق بن عبد القادر",
    "charges": "التهديد بالقتل (المادة 287 قانون العقوبات)",
    "facts": """
    نشب خلاف بين المتهم وجاره (المجني عليه) حول مكان ركن السيارة.
    تطور النقاش إلى صياح، وقال المتهم: "سأقتلك إن لم تبتعد".
    المتهم يدعي أنه كان في حالة غضب شديد ولم يقصد التنفيذ.
    المجني عليه قدم شكوى فورية.
    لا يوجد شهود محايدون، فقط زوجة المجني عليه.
    لم يتم ضبط أي سلاح مع المتهم.
    """,
    "legal_context": """
    [المادة 287 قانون العقوبات]: كل من هدد غيره بالقتل كتابة أو مشافهة... يعاقب بالحبس.
    [اجتهاد المحكمة العليا 1998]: التهديد المعاقب عليه هو الذي يلقي الرعب في نفس الضحية ويكون مصحوباً بعزم الجاني على التنفيذ. مجرد الألفاظ العابرة في وقت الغضب لا تشكل الجناية إذا انتفت نية التنفيذ.
    [المادة 212 إجراءات جزائية]: الإثبات حر في المواد الجزائية، والشك يفسر لمصلحة المتهم.
    """
}

# --- PROMPT ENGINEERING (Optimized for Gemini Pro) ---
prompt = f"""
بصفتك محامياً "نابغاً" (Elite Lawyer) لدى المحكمة العليا، قم بصياغة **مذكرة دفاع** قانونية محكمة للمتهم.
استخدم قدراتك في "الاستدلال المنطقي" (Reasoning) لربط الوقائع بالنصوص القانونية.

معلومات القضية:
- الجهة القضائية: {mock_case_data['court']}
- المتهم: {mock_case_data['defendant']}
- التهمة: {mock_case_data['charges']}
- الوقائع: {mock_case_data['facts']}

السند القانوني المتاح:
{mock_case_data['legal_context']}

⚠️ تعليمات صارمة (Style Guide):
1. ابدأ بـ "إلى السيد رئيس محكمة الجنايات والسادة المستشارين المحترمين".
2. استخدم لغة قانونية فخمة (رصينة).
3. الهيكل: الوقائع -> المناقشة (الشكل والموضوع) -> الطلبات.
4. **أهم نقطة**: ناقش "الركن المعنوي" (القصد الجنائي) بذكاء استناداً لاجتهاد المحكمة العليا المذكور، وكيف أن "الغضب العابر" ينفي نية القتل.

ابدأ المرافعة الآن:
"""

try:
    model = genai.GenerativeModel(MODEL_NAME)
    print("⏳ Generating Pleading (This may take 10-20 seconds for deep reasoning)...")
    
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.3, # Low temperature for legal precision
            max_output_tokens=4096 # Allow long Output
        )
    )
    
    print("\n" + "="*40)
    print("📜 المرافعة المُولَّدة (Gemini Pro)")
    print("="*40 + "\n")
    print(response.text)
    print("\n" + "="*40)
    print("✅ تم التوليد بنجاح!")

except Exception as e:
    print(f"❌ Error: {e}")
