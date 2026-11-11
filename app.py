import streamlit as st
import yt_dlp
import cv2
import os
import glob
from PIL import Image
from google import genai

# --- पेज कॉन्फ़िगरेशन (मोबाइल फ्रेंडली) ---
st.set_page_config(page_title="Reel Fashion Finder", page_icon="👗", layout="centered")

st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 3em;
        background-color: #FF4B4B;
        color: white;
        font-weight: bold;
    }
    .platform-card {
        padding: 12px;
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        margin-bottom: 10px;
        background-color: #f9f9f9;
    }
    </style>
""", unsafe_allow_html=True)

st.title("👗 Reel Fashion Finder")
st.caption("Instagram Reel से कपड़े पहचानें और Meesho, Amazon, Myntra आदि पर ढूँढें")

# --- एफिलिएट ID सेटिंग्स (जरूरत अनुसार बदलें) ---
AFFILIATE_TAGS = {
    "amazon": "YOUR_AMAZON_TAG-21",      # अपना Amazon Associates ID डालें
    "flipkart": "YOUR_FLIPKART_ID",     # अपना Flipkart Affiliate ID डालें
    "meesho": "",                       # Meesho डायरेक्ट लिंक (या अर्निग लिंक शॉर्टनर)
    "myntra": "",                       # Cuelinks/EarnKaro रूटिंग के लिए
    "ajio": ""
}

# --- 1. रील से मुख्य फ्रेम निकालने का फ़ंक्शन ---
def extract_frame_from_reel(reel_url):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': 'temp_reel.%(ext)s',
        'quiet': True,
        'no_warnings': True
    }
    
    # पुरानी फाइलें साफ करें
    for f in glob.glob("temp_reel*") + ["extracted_frame.jpg"]:
        if os.path.exists(f):
            os.remove(f)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([reel_url])

    video_file = glob.glob("temp_reel.*")
    if not video_file:
        return None

    cap = cv2.VideoCapture(video_file[0])
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # वीडियो के 25% हिस्से से एक साफ़ फ्रेम निकालें
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(1, total_frames // 4))
    success, frame = cap.read()
    cap.release()

    if success:
        frame_path = "extracted_frame.jpg"
        cv2.imwrite(frame_path, frame)
        return frame_path
    return None

# --- 2. AI से कपड़ों की पहचान ---
def detect_fashion_item(image_path, api_key):
    client = genai.Client(api_key=api_key)
    image = Image.open(image_path)
    
    prompt = (
        "Identify the primary clothing or outfit worn by the person in this image. "
        "Return ONLY a clean, precise 4-6 word e-commerce search query describing it "
        "(e.g., 'women floral print anarkali kurta', 'oversized pink crop hoodie', 'embroidered georgette saree'). "
        "Do not include quotes, punctuation, or extra words."
    )
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[image, prompt]
    )
    return response.text.strip()

# --- 3. शॉपिंग और एफिलिएट लिंक्स जनरेटर ---
def generate_platform_links(query):
    encoded_query = requests.utils.quote(query)
    
    links = {
        "Meesho": {
            "url": f"https://www.meesho.com/search?q={encoded_query}",
            "color": "#9b27b0",
            "desc": "बजट और ट्रेंडी कलेक्शन"
        },
        "Amazon": {
            "url": f"https://www.amazon.in/s?k={encoded_query}&tag={AFFILIATE_TAGS['amazon']}",
            "color": "#ff9900",
            "desc": "फास्ट डिलीवरी और वैरायटी"
        },
        "Flipkart": {
            "url": f"https://www.flipkart.com/search?q={encoded_query}&affid={AFFILIATE_TAGS['flipkart']}",
            "color": "#2874f0",
            "desc": "टॉप डील्स और ऑफर्स"
        },
        "Myntra": {
            "url": f"https://www.myntra.com/{encoded_query}",
            "color": "#ff3f6c",
            "desc": "प्रीमियम ब्रांडेड फैशन"
        },
        "Ajio": {
            "url": f"https://www.ajio.com/search/?text={encoded_query}",
            "color": "#2c4152",
            "desc": "ट्रेंडी वेस्टर्न और एथनिक"
        }
    }
    return links

# --- मुख्य UI ---
api_key = st.text_input("Gemini API Key डालें:", type="password", help="aistudio.google.com से फ्री में ले सकते हैं")
reel_url = st.text_input("Instagram Reel Link यहाँ पेस्ट करें:", placeholder="https://www.instagram.com/reel/...")

if st.button("प्रोडक्ट ढूँढें 🔍"):
    if not api_key:
        st.warning("कृपया पहले अपनी Gemini API Key दर्ज करें।")
    elif not reel_url or "instagram.com" not in reel_url:
        st.warning("कृपया एक वैध Instagram Reel URL दर्ज करें।")
    else:
        with st.spinner("रील से फ्रेम निकाला जा रहा है..."):
            frame_path = extract_frame_from_reel(reel_url)
            
        if not frame_path:
            st.error("रील प्रोसेस नहीं हो सकी। लिंक चेक करें या सुनिश्चित करें कि रील पब्लिक है।")
        else:
            st.image(frame_path, caption="पहचाना गया फ्रेम", use_container_width=True)
            
            with st.spinner("AI कपड़े और स्टाइल को पहचान रहा है..."):
                product_query = detect_fashion_item(frame_path, api_key)
                
            st.success(f"**पहचाना गया प्रोडक्ट:** {product_query}")
            st.markdown("### 🛒 उपलब्ध प्लेटफॉर्म्स:")

            platform_links = generate_platform_links(product_query)
            for name, details in platform_links.items():
                st.markdown(f"""
                <div class="platform-card">
                    <strong style="color: {details['color']}; font-size: 1.1em;">{name}</strong> - <span>{details['desc']}</span><br>
                    <a href="{details['url']}" target="_blank" style="text-decoration: none; font-weight: bold; color: #1e88e5;">
                        👉 {name} पर यह प्रोडक्ट देखें
                    </a>
                </div>
                """, unsafe_allow_html=True)
