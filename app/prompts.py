import re

ROLES=["hook","product_demo","lifestyle","detail","benefit","proof","cta"]
DIRECTIONS={
"hook":"Reveal the product on a simple table; slow camera push-in.",
"product_demo":"Hand-held product demo, gently rotate the product; steady close camera tracking.",
"lifestyle":"Show the product in an everyday setting without implying undocumented use; gentle lateral pan.",
"detail":"Show only documented visible details; slow macro camera move.",
"benefit":"Demonstrate only an approved evidenced benefit; if none exists, show the product from another angle; slow orbit.",
"proof":"Show visible physical details, never fabricate tests, testimonials or certifications; locked camera with subtle push-in.",
"cta":"Clean product end shot with blank space for a CTA added during editing; static camera.",
"cleaning_handling":"Gentle dry handling only unless an approved instruction supports cleaning; close camera tracking."
}
NEGATIVE="no fake text; no fake logos; no extra accessories; no deformation; no unsupported claims; no brand/logo changes"
SENSITIVE=re.compile(r"\b(?:water.?proof|medical|certif\w*|cooling|heating|health|performance|safe(?:ty)?|cures?|treats?|kills? bacteria|cold|hot)\b|กันน้ำ|รักษา|สุขภาพ|ปลอดภัย|รับรอง|เย็น|ร้อน|ประสิทธิภาพ|ฆ่าเชื้อ",re.I)
PROHIBITED=re.compile(r"fake (?:review|certification)|guaranteed cure|รีวิวปลอม|รักษาหายแน่นอน",re.I)

def classify(fact, source, status, notes):
    if status not in {"verified","seller_claim","unverified","prohibited"}:
        raise ValueError("Unknown verification status")
    if PROHIBITED.search(fact):
        return "prohibited"
    if status=="verified":
        if not source.strip() or not notes.strip():
            raise ValueError("Verified facts require evidence source and review notes")
        return "verified"
    if SENSITIVE.search(fact) and status!="prohibited":
        return "unverified"
    return status

def identity(facts):
    found={}
    for fact in facts:
        key,sep,value=fact.fact.partition(":")
        if sep and key.strip().lower() in {"color","shape","size","accessories"} and value.strip():
            found[key.strip().lower()]=value.strip()
    if len(found)!=4:
        raise ValueError("Verified facts must include color:, shape:, size:, accessories: (use none if evidenced)")
    return found

def prompt_for(product, facts, role, audience, tone):
    description="; ".join(f.fact for f in facts)
    return (f"Exact product identity: {product}. Approved facts: {description}. "
            f"Portrait 9:16, 8-second target duration, realistic UGC/lifestyle. "
            f"{DIRECTIONS[role]} Audience: {audience}; tone: {tone}. "
            f"Maintain the same product color, shape, size, accessories and logo throughout all shots. "
            f"Show only approved facts; product identity is not guaranteed and requires manual review. {NEGATIVE}.")

def check_sensitive_claims(text, facts, role=None):
    cleaned = text
    trusted_phrases = [
        "never fabricate tests, testimonials or certifications",
        "no fake text",
        "no fake logos",
        "no extra accessories",
        "no deformation",
        "no unsupported claims",
        "no brand/logo changes"
    ]
    if role and role in DIRECTIONS:
        trusted_phrases.append(DIRECTIONS[role])
    for phrase in trusted_phrases:
        cleaned = cleaned.replace(phrase, "")
    
    fact_text = " ".join(f.fact.casefold() for f in facts)
    for match in SENSITIVE.finditer(cleaned):
        if match.group().casefold() not in fact_text:
            raise ValueError("Prompt contains a sensitive claim without an approved evidenced fact")


