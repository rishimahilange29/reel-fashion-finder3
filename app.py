import streamlit as st
import yt_dlp
import cv2
import os
import json
import re
import numpy as np
from PIL import Image
from google import genai
from google.genai import types

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
    .product-box {
        padding: 16px;
        border-radius: 10px;
        border: 1px solid #e0e0e0;
        margin-bottom: 20px;
        background-color: #ffffff;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    .store-tag {
        display: inline-block;
        padding: 6px 12px;
        margin: 4px 6px 4px 0;
        background-color: #f1f3f4;
        border-radius: 6px;
        text-decoration: none;
        color: #1a73e8;
        font-weight: bold;
        border: 1px solid #d2e3fc;
    }
    </style>
""", unsafe_allow_html=True)

st.title("👗 Reel Fashion Finder")
st.caption("एक रील के सभी अलग-अलग कपड़े पहचानें और सीधे शॉपिंग लिंक्स प्राप्त करें")

# --- 1. सुपरफास्ट मल्टी-फ्रेम एक्सट्रैक्टर ---
def extract_multiple_unique_frames(reel_url, max_frames=4):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(reel_url, download=False)
        stream_url = info.get('url')

    if not stream_url:
        raise ValueError("रील का मीडिया URL नहीं मिल सका।")

    cap = cv2.VideoCapture(stream_url)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        total_frames = 150

    # रील के अलग-अलग टाइमस्टैम्प्स (शुरुआत, मध्य और अंत) से फ्रेम चुनना
    ratios = [0.15, 0.40, 0.65, 0.85]
    saved_frames = []
    last_gray = None

    for i, ratio in enumerate(ratios):
        target_idx = int(total_frames * ratio)
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_idx)
        success, frame = cap.read()

        if success and frame is not None:
            # स्पीड बढ़ाने के लिए साइज थोड़ा छोटा करें
            height, width = frame.shape[:2]
            scale = 640 / max(height, width)
            resized = cv2.resize(frame, (int(width * scale), int(height * scale)))
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

            # अगर नया फ्रेम पिछले फ्रेम से अलग है (अलग सीन/कपड़े), तभी जोड़ें
            if last_gray is None or np.mean(cv2.absdiff(gray, last_gray)) > 25:
                path = f"/tmp/frame_{i}.jpg"
                cv2.imwrite(path, resized, [cv2.IMWRITE_JPEG_QUALITY, 85])
                saved_frames.append(path)
                last_gray = gray

        if len(saved_frames) >= max_frames:
            break

    cap.release()
    return saved_frames

# --- 2. सिंगल-शॉट फास्ट AI डिटेक्शन ---
def detect_all_fashion_items(image_paths, api_key):
    client = genai.Client(api_key=api_key.strip())
    
    pil_images = [Image.open(p) for p in image_paths]

    prompt = """
    You are an expert fashion cataloguer for Indian e-commerce.
    Analyze the provided images extracted from an Instagram reel.
    For each distinct clothing outfit shown across these images:
    1. Identify what it is (color, fabric, style, type e.g., 'Embroidered Anarkali Kurta Set', 'Casual Oversized Crop Top').
    2. Provide clean direct shopping search queries and target store links for platforms popular in India (Meesho, Amazon India, Myntra, Flipkart, Ajio).

    Return ONLY a valid JSON array of objects. Do not wrap in markdown quotes or backticks.
    Format:
    [
      {
        "item_title": "Descriptive name of Outfit 1",
        "description": "Short 1-line style details",
        "stores": [
          {
            "platform": "Myntra",
            "url": "https://www.myntra.com/exact-search-query",
            "price_range": "₹599 - ₹999"
          },
          {
            "platform": "Meesho",
            "url": "https://www.meesho.com/search?q=exact-search-query",
            "price_range": "₹350 - ₹500"
          },
          {
            "platform": "Amazon",
            "url": "https://www.amazon.in/s?k=exact-search-query",
            "price_range": "₹699 - ₹1200"
          }
        ]
      }
    ]
    """

    contents = pil_images + [prompt]

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=0.1
        )
    )

    clean_text = response.text.strip()
    match = re.search(r'\[.*\]', clean_text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    
    return []

# --- 3. मुख्य इंटरफ़ेस ---
api_key = st.text_input("Gemini API Key डालें:", type="password", help="aistudio.google.com से प्राप्त करें")
reel_url = st.text_input("Instagram Reel Link यहाँ पेस्ट करें:", placeholder="https://www.instagram.com/reel/...")

if st.button("सभी प्रोडक्ट्स ढूँढें 🔍"):
    clean_key = api_key.strip() if api_key else ""
