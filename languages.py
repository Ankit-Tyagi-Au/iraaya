"""Languages iRaaya can answer and speak in.

gtts_code: language code for Google Text-to-Speech (gTTS)
el_code:   ISO 639 code for ElevenLabs
display:   the language's own name, shown to users
greeting:  spoken by the voice preview button
"""

LANGUAGES = {
    "English": {
        "greeting": "Hello, I am iRaaya. Ask me anything about your business.",
        "gtts_code": "en",
        "el_code": "en",
        "display": "English"
    },
    "Hindi": {
        "greeting": "नमस्ते, मैं आइराया हूँ। अपने व्यापार के बारे में मुझसे कुछ भी पूछिए।",
        "gtts_code": "hi",
        "el_code": "hi",
        "display": "हिंदी"
    },
    "Mandarin Chinese": {
        "greeting": "你好，我是 iRaaya。关于你的生意，尽管问我。",
        "gtts_code": "zh-CN",
        "el_code": "zh",
        "display": "中文"
    },
    "Arabic": {
        "greeting": "مرحبًا، أنا آيرايا. اسألني أي شيء عن عملك.",
        "gtts_code": "ar",
        "el_code": "ar",
        "display": "العربية"
    },
    "Vietnamese": {
        "greeting": "Xin chào, tôi là iRaaya. Hãy hỏi tôi bất cứ điều gì về việc kinh doanh của bạn.",
        "gtts_code": "vi",
        "el_code": "vi",
        "display": "Tiếng Việt"
    },
    "Korean": {
        "greeting": "안녕하세요, 저는 아이라야입니다. 사업에 대해 무엇이든 물어보세요.",
        "gtts_code": "ko",
        "el_code": "ko",
        "display": "한국어"
    },
    "Japanese": {
        "greeting": "こんにちは、アイラーヤです。ビジネスについて何でも聞いてください。",
        "gtts_code": "ja",
        "el_code": "ja",
        "display": "日本語"
    },
    "Spanish": {
        "greeting": "Hola, soy iRaaya. Pregúntame lo que quieras sobre tu negocio.",
        "gtts_code": "es",
        "el_code": "es",
        "display": "Español"
    },
    "French": {
        "greeting": "Bonjour, je suis iRaaya. Posez-moi toutes vos questions sur votre entreprise.",
        "gtts_code": "fr",
        "el_code": "fr",
        "display": "Français"
    },
    "Italian": {
        "greeting": "Ciao, sono iRaaya. Chiedimi qualsiasi cosa sulla tua attività.",
        "gtts_code": "it",
        "el_code": "it",
        "display": "Italiano"
    },
    "Portuguese": {
        "greeting": "Olá, eu sou a iRaaya. Pergunte-me qualquer coisa sobre o seu negócio.",
        "gtts_code": "pt",
        "el_code": "pt",
        "display": "Português"
    },
    "Filipino": {
        "greeting": "Kumusta, ako si iRaaya. Magtanong ka ng kahit ano tungkol sa iyong negosyo.",
        "gtts_code": "tl",
        "el_code": "fil",
        "display": "Filipino"
    },
    "Greek": {
        "greeting": "Γεια σας, είμαι η iRaaya. Ρωτήστε με οτιδήποτε για την επιχείρησή σας.",
        "gtts_code": "el",
        "el_code": "el",
        "display": "Ελληνικά"
    }
}
