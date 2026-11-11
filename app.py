import streamlit as st
import yt_dlp
import cv2
import os
import json
import re
from PIL import Image
from google import genai
from google.genai import types

# --- पेज कॉन्फ़िगरेशन ---
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
        padding: 14px;
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        margin-bottom: 12px;
        background-color: #ffffff;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    </style>
""", unsafe_allow_html=True)

st.title("👗 Reel Fashion Finder")
st.caption("Instagram Reel से कपड़े पहचानें और सीधे प्रोडक्ट लिंक प्राप्त करें")

# --- 1. बिना वीडियो डाउनलोड किए सबसे साफ़ फ्रेम निकालना ---
def extract_best_frame_from_stream(reel_url):
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(reel_url, download=False)
        stream_url = info.get('url')

    if not stream_url:
        raise ValueError("रील का सीधा वीडियो स्ट्रीम URL नहीं मिल सका।")

    cap = cv2.VideoCapture(stream_url)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        total_frames = 120

    sample_ratios = [0.25, 0.50, 0.75]
    best_frame = None
    max_sharpness = -1

    for ratio in sample_ratios:
        frame_idx = int(total_frames * ratio)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        success, frame = cap.read()

        if success and frame is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
            if sharpness > max_sharpness:
                max_sharpness = sharpness
                best_frame = frame

    cap.release()

    if best_frame is None:
        raise ValueError("रील से कोई साफ़ फ्रेम नहीं निकाला जा सका।")

    frame_path = "/tmp/best_fashion_frame.jpg"
    cv2.imwrite(frame_path, best_frame)
    return frame_path

# --- 2. स्टेप 1: इमेज देखकर कपड़ों की पहचान करना ---
def identify_fashion_from_image(image_path, client):
    image = Image.open(image_path)
    prompt = (
        "Focus only on the primary outfit or clothing worn in this image. "
        "Describe it precisely as an Indian e-commerce search query with color, fabric, pattern, and dress type "
        "(e.g., 'women floral printed cotton anarkali kurta with dupatta' or 'men oversized graphic print black hoodie'). "
        "Output ONLY the descriptive product name in one line, nothing else."
    )
    
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[image, prompt]
    )
    return response.text.strip()

# --- 3. स्टेप 2: लाइव वेब पर शॉपिंग लिंक्स ढूँढना ---
def search_product_links(product_name, client):
    prompt = f"""
    Search the web for shopping listings in India for this exact product: "{product_name}".
    Find direct buying or product search links on platforms like Meesho, Amazon India, Myntra, Flipkart, Ajio, and Nykaa Fashion.
    
    Return ONLY a raw JSON object with this exact structure:
    {{
      "product_name": "{product_name}",
      "stores": [
        {{
          "platform": "Store name (e.g. Myntra, Meesho, Amazon)",
          "direct_url": "Direct product link or clean search URL",
          "price_estimate": "Price with ₹ if found, else empty string"
        }}
      ]
    }}
    Do NOT include markdown backticks or explanations. Output pure JSON only.
    """

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[{"google_search": {}}],
            temperature=0.1
        )
    )

    raw_text = response.text.strip()
    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if match:
        clean_json = match.group(0)
        return json.loads(clean_json)
    
    return {"product_name": product_name, "stores": []}

# --- मुख्य UI ---
api_key = st.text_input("Gemini API Key डालें:", type="password", help="aistudio.google.com से प्राप्त करें")
reel_url = st.text_input("Instagram Reel Link यहाँ पेस्ट करें:", placeholder="https://www.instagram.com/reel/...")

if st.button("प्रोडक्ट ढूँढें 🔍"):
    clean_key = api_key.strip() if api_key else ""
    if not clean_key:
        st.warning("कृपया पहले अपनी Gemini API Key दर्ज करें।")
    elif not reel_url or "instagram.com" not in reel_url:
        st.warning("कृपया एक वैध Instagram Reel URL दर्ज करें।")
    else:
        frame_path = None
        with st.spinner("रील से सबसे साफ़ प्रोडक्ट फ्रेम छाँटा जा रहा है..."):
            try:
                frame_path = extract_best_frame_from_stream(reel_url)
            except Exception as e:
                st.error(f"फ्रेम निकालने में समस्या: {e}")

        if frame_path:
            st.image(frame_path, caption="पहचाना गया फ्रेम", use_container_width=True)

            try:
                client = genai.Client(api_key=clean_key)

                with st.spinner("AI कपड़ों की पहचान कर रहा है..."):
                    detected_product = identify_fashion_from_image(frame_path, client)

                with st.spinner(f"'{detected_product}' के लिए लाइव शॉपिंग लिंक्स ढूँढे जा रहे हैं..."):
                    result = search_product_links(detected_product, client)
                    product_title = result.get("product_name", detected_product)
                    stores = result.get("stores", [])

                st.success(f"**पहचाना गया प्रोडक्ट:** {product_title}")
                st.markdown("### 🛒 उपलब्ध प्लेटफॉर्म्स और डायरेक्ट लिंक्स:")

                if stores:
                    for s in stores:
                        name = s.get("platform", "Shopping Store")
                        url = s.get("direct_url", "#")
                        price = s.get("price_estimate", "")
                        price_display = f" — <b>{price}</b>" if price else ""

                        st.markdown(f"""
                        <div class="platform-card">
                            <b style="font-size: 1.1em; color: #111;">{name}</b>{price_display}<br>
                            <a href="{url}" target="_blank" style="text-decoration: none; font-weight: bold; color: #0066cc;">
                                👉 {name} पर सीधे देखें / खरीदें
                            </a>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("लाइव स्टोर्स के डायरेक्ट लिंक्स नहीं मिले।")

            except Exception as err:
                st.error(f"API प्रोसेस करने में त्रुटि: {err}")
                
