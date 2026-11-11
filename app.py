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

# --- 1. रील डाउनलोड करके सबसे बेहतरीन फ्रेम छाँटना ---
def extract_best_frame_from_reel(reel_url):
    download_dir = "/tmp/reel_temp"
    os.makedirs(download_dir, exist_ok=True)
    video_path = os.path.join(download_dir, "input_reel.mp4")
    frame_path = "/tmp/best_product_frame.jpg"

    # पुरानी फाइलें साफ करें
    for p in [video_path, frame_path]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': video_path,
        'nopart': True,
        'overwrites': True,
        'quiet': True,
        'no_warnings': True,
    }

    # वीडियो को डिस्क पर सुरक्षित सेव करें
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([reel_url])

    if not os.path.exists(video_path) or os.path.getsize(video_path) == 0:
        raise ValueError("वीडियो डाउनलोड नहीं हो सकी। कृपया सुनिश्चित करें कि रील पब्लिक है।")

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    if total_frames <= 0:
        total_frames = 60

    # 20%, 40%, 60%, 80% में से सबसे शार्प फ्रेम चुनें
    sample_ratios = [0.20, 0.40, 0.60, 0.80]
    best_frame = None
    max_sharpness = -1

    for r in sample_ratios:
        target_idx = int(total_frames * r)
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_idx)
        ret, frame = cap.read()
        if ret and frame is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
            if sharpness > max_sharpness:
                max_sharpness = sharpness
                best_frame = frame

    if best_frame is None:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, best_frame = cap.read()

    cap.release()

    # वीडियो फाइल को तुरंत हटाएं ताकि स्टोरेज खाली रहे
    if os.path.exists(video_path):
        os.remove(video_path)

    if best_frame is None:
        raise ValueError("वीडियो से कोई भी फ्रेम रीड नहीं हो सका।")

    cv2.imwrite(frame_path, best_frame)
    return frame_path

# --- 2. विज़न मॉडल से कपड़े की सटीक पहचान ---
def identify_fashion_item(image_path, client):
    image = Image.open(image_path)
    prompt = (
        "Look at the clothing or outfit worn in this image. "
        "Describe it precisely as an Indian e-commerce search query with dress type, color, print, and style "
        "(e.g., 'women floral printed georgette anarkali kurta with dupatta' or 'men oversized black graphic hoodie'). "
        "Output ONLY the descriptive product name in one single line without punctuation."
    )

    # gemini-3.8-flash पर अपडेट किया गया
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=[image, prompt]
    )
    return response.text.strip()

# --- 3. वेब सर्च के ज़रिए शॉपिंग स्टोर्स और लिंक्स ढूँढना ---
def search_stores_for_outfit(product_name, client):
    prompt = f"""
    Search online stores in India (like Meesho, Myntra, Amazon India, Flipkart, Ajio) for this fashion product: "{product_name}".
    Return a valid JSON object listing matching platforms and direct search or product URLs.
    
    Format:
    {{
      "product_name": "{product_name}",
      "stores": [
        {{
          "platform": "Store name (e.g. Myntra, Meesho, Amazon)",
          "direct_url": "Direct product link or store search URL",
          "price_estimate": "Estimated price with ₹ symbol if found"
        }}
      ]
    }}
    Output strictly raw JSON only. Do not add markdown backticks.
    """

    # gemini-3.8-flash पर अपडेट किया गया
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[{"google_search": {}}],
            temperature=0.2
        )
    )

    raw_text = response.text.strip()
    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    
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
        
        with st.status("रील प्रोसेस हो रही है...", expanded=True) as status:
            st.write("📥 रील से सबसे साफ़ प्रोडक्ट फ्रेम निकाला जा रहा है...")
            try:
                frame_path = extract_best_frame_from_reel(reel_url)
                st.write("✅ सबसे साफ़ फ्रेम निकाल लिया गया!")
            except Exception as e:
                st.error(f"रील से फ्रेम निकालने में त्रुटि: {e}")
                status.update(label="त्रुटि हुई!", state="error")

            if frame_path:
                st.image(frame_path, caption="पहचाना गया फ्रेम", use_container_width=True)
                
                try:
                    client = genai.Client(api_key=clean_key)

                    st.write("🤖 AI कपड़ों और डिज़ाइन की पहचान कर रहा है...")
                    product_name = identify_fashion_item(frame_path, client)
                    st.write(f"👗 **पहचाना गया:** {product_name}")

                    st.write("🌐 Meesho, Myntra, Amazon पर लाइव लिंक्स खोजे जा रहे हैं...")
                    search_result = search_stores_for_outfit(product_name, client)
                    stores = search_result.get("stores", [])

                    status.update(label="सर्च पूरी हुई!", state="complete")

                    st.success(f"**पहचाना गया ऑउटफिट:** {product_name}")
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
                        st.info("इस प्रोडक्ट के लिए सीधे लिंक्स नहीं मिल पाए।")

                except Exception as err:
                    st.error(f"AI प्रोसेसिंग में समस्या: {err}")
                    status.update(label="API त्रुटि!", state="error")
      
