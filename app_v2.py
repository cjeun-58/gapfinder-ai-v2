import streamlit as st
from google import genai
import pandas as pd
from PyPDF2 import PdfReader
from python_pptx import Presentation
import requests
from bs4 import BeautifulSoup
from fpdf import FPDF
import io
import os
import re
from PIL import Image
import pytesseract

# --- 1. 페이지 설정 및 데이터 초기화 ---
_ = st.set_page_config(page_title="GapFinder v2 (v21.5)", layout="wide")

# 사이드바 ✅ 표시를 위한 세션 데이터 관리
states = ['brand_analysis', 'brand_insight', 'comp_analysis', 'consumer_data', 'consumer_analysis', 'final_report']
for key in states:
    if key not in st.session_state:
        st.session_state[key] = "" if 'analysis' in key or 'report' in key else []
if 'brand_insight' not in st.session_state:
    st.session_state['brand_insight'] = ""

# --- 2. 사이드바 (API 설정 및 분석 현황) ---
with st.sidebar:
    st.header("🔑 서비스 설정")
    gemini_key = st.text_input("1. Gemini API Key", type="password")
    serper_key = st.text_input("2. Serper API Key", type="password")
    
    st.divider()
    st.subheader("🇳 네이버 검색 API (선택)")
    naver_id = st.text_input("Naver Client ID")
    naver_secret = st.text_input("Naver Client Secret", type="password")
    
    _ = st.divider()
    menu = st.radio("전략 수립 단계", [
        "1단계. 브랜드 분석 (Thesis)", 
        "1.5단계. 경쟁사 분석 (3 Sets)", 
        "2단계. 소비자 데이터 (Multi-Source)", 
        "3단계. 통합 전략 및 PDF"
    ])
    
    _ = st.divider()
    st.subheader("📊 실시간 분석 현황")
    st.write(f"🏢 브랜드: {'✅' if st.session_state['brand_analysis'] else '❌'}")
    st.write(f"⚔️ 경쟁사: {'✅' if st.session_state['comp_analysis'] else '❌'}")
    st.write(f"👥 소비자: {'✅' if st.session_state['consumer_analysis'] else '❌'}")

# --- 3. 핵심 유틸리티 함수 (OCR & Naver API 통합) ---

def get_media_tag(url):
    """URL 기반 매체 태그 분류"""
    if "blog.naver.com" in url: return "[🟢네이버 블로그]"
    elif "cafe.naver.com" in url: return "[🔵네이버 카페]"
    elif "youtube.com" in url or "youtu.be" in url: return "[🔴유튜브]"
    else: return "[⚪구글/기타]"

def extract_content_all(files=None, url=""):
    """문서(PDF/PPTX) 및 이미지(OCR) 텍스트 추출"""
    text = ""
    if files:
        for f in files:
            try:
                if f.name.endswith(".pdf"):
                    text += "\n".join([p.extract_text() for p in PdfReader(f).pages if p.extract_text()])
                elif f.name.endswith(".pptx"):
                    text += "\n".join([s.text for slide in Presentation(f).slides for s in slide.shapes if hasattr(s, "text")])
                elif f.name.lower().endswith((".png", ".jpg", ".jpeg")):
                    # [v21.5 핵심] 이미지 내 한글 텍스트 추출
                    img = Image.open(f)
                    text += f"\n[이미지 {f.name} OCR 결과]:\n" + pytesseract.image_to_string(img, lang='kor+eng')
            except: pass
    if url:
        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            for s in soup(['script', 'style']): s.decompose()
            text += f"\n[URL: {url}]\n{soup.get_text()[:3000]}"
        except: pass
    return text

def search_naver_api(query, target="blog"):
    """네이버 공식 API 검색"""
    if not naver_id or not naver_secret: return []
    headers = {"X-Naver-Client-Id": naver_id, "X-Naver-Client-Secret": naver_secret}
    url = f"https://openapi.naver.com/v1/search/{target}.json?query={query}&display=10"
    try:
        res = requests.get(url, headers=headers).json()
        return [f"[🟢네이버 {target}] {i['title']}: {i['description']}" for i in res.get('items', [])]
    except: return []

def run_ai_analysis(data, step, insight="", brand_ctx="", consumer_raw=""):
    """'짱'의 시각을 반영한 전략 분석 엔진  [cite: 414-417, 590]"""
    if not gemini_key: return "⚠️ Gemini API Key가 필요합니다."
    try:
        client = genai.Client(api_key=gemini_key)
        p_base = "인사말 생략. 광고 대행사 총괄 기획자로서 분석하세요. 리스트 형식을 사용하세요.\n\n"
        
        prompts = {
            "brand": f"{p_base}[Thesis] 자사 브랜드 분석. 강점, 포지션, 소비자 접근 언어를 도출하세요. 인사이트: {insight}",
            "comp": f"{p_base}[Competitor] 입력된 경쟁사만 분석하세요. 자사({brand_ctx[:200]})와 대비하여 비어 있는 기회(White Space)를 찾으세요.",
            "consumer": f"{p_base}[Antithesis] 네이버/구글/유튜브 통합 데이터 분석. 소비자의 날것의 페인포인트와 채널별 특징을 도출하세요.",
            "final": f"{p_base}[Victory Strategy v6.5]\n1. 브랜드 vs 소비자 언어 Gap 분석 (워딩 대조)\n2. 경쟁사 대비 White Space\n3. 타겟별 필승 광고 카피\n4. 최종 결론: '자괴감을 자부심으로 전환'하는 식의 선언적 필승 전략 한 문장 정의\n인사이트: {insight}\n데이터: {consumer_raw[:5000]}"
        }
        res = client.models.generate_content(model="gemini-3-flash-preview", contents=prompts[step] + "\n\n데이터:\n" + data[:12000])
        return res.text
    except Exception as e: return f"분석 중 오류 발생: {e}"

# --- 4. 무결점 PDF 엔진 (Iron Guard v21.5) ---

class PiecePDF(FPDF):
    def __init__(self):
        super().__init__()
        f_reg, f_bold = "NanumGothic.ttf", "NanumGothicBold.ttf"
        if os.path.exists(f_reg):
            self.add_font('NG', '', f_reg); self.add_font('NG', 'B', f_bold); self.fn = 'NG'
        else: self.fn = 'Arial'
        _ = self.set_auto_page_break(auto=True, margin=20)
        _ = self.set_margins(20, 20, 20)

    def write_smart(self, title, content):
        if not content: return
        self.add_page()
        self.set_font(self.fn, 'B', 16); self.set_text_color(0, 51, 102)
        self.cell(170, 15, txt=title, ln=True, align='C'); self.ln(5)
        self.set_font(self.fn, '', 10); self.set_text_color(50, 50, 50)
        # 너비 170mm 고정하여 잘림 방지
        clean_text = re.sub(r'[^\u0000-\u007f\uac00-\ud7af]', '', content.replace('|', ' '))
        self.multi_cell(170, 7, txt=clean_text)

# --- 5. UI 단계별 실행 로직 ---

if menu == "1단계. 브랜드 분석 (Thesis)":
    st.title("🏢 1단계. 브랜드(자사) 분석")
    b_f = st.file_uploader("자사 자료 (문서/이미지)", accept_multiple_files=True)
    b_u = st.text_input("자사 랜딩페이지 URL")
    st.session_state['brand_insight'] = st.text_area("💡 실제 운영 인사이트", value=st.session_state['brand_insight'])
    if st.button("브랜드 분석 시작"):
        with st.spinner("이미지 OCR 및 데이터 추출 중..."):
            st.session_state['brand_analysis'] = run_ai_analysis(extract_content_all(b_f, b_u), "brand", st.session_state['brand_insight'])
            _ = st.rerun()
    st.markdown(st.session_state['brand_analysis'])

elif menu == "1.5단계. 경쟁사 분석 (3 Sets)":
    st.title("⚔️ 1.5단계. 경쟁사 정밀 분석")
    col1, col2 = st.columns([1, 2])
    with col1: c1n = st.text_input("경쟁사 1"); c2n = st.text_input("경쟁사 2"); c3n = st.text_input("경쟁사 3")
    with col2: c1u = st.text_input("경쟁사 1 URL"); c2u = st.text_input("경쟁사 2 URL"); c3u = st.text_input("경쟁사 3 URL")
    if st.button("경쟁사 분석 시작"):
        with st.spinner("지정 브랜드 탐색 중..."):
            all_c = ""
            for n, u in [(c1n, c1u), (c2n, c2u), (c3n, c3u)]:
                if n:
                    res = requests.post("https://google.serper.dev/search", headers={'X-API-KEY': serper_key}, json={"q": f"{n} 특징 마케팅", "gl": "kr", "hl": "ko"}).json()
                    all_c += f"\n[{n}]\n" + "\n".join([r.get('snippet', '') for r in res.get('organic', [])])
            st.session_state['comp_analysis'] = run_ai_analysis(all_c, "comp", brand_ctx=st.session_state['brand_analysis'])
            _ = st.rerun()
    st.markdown(st.session_state['comp_analysis'])

elif menu == "2단계. 소비자 데이터 (Multi-Source)":
    st.title("👥 2단계. 네이버 & 구글 통합 소비자 데이터")
    kw = st.text_input("분석 키워드 (쉼표 구분)")
    if st.button("데이터 수집 시작"):
        with st.spinner("네이버 API 및 구글 데이터 수집 중..."):
            all_r = []
            for k in [x.strip() for x in kw.split(",")]:
                # 네이버 블로그/카페 수집
                all_r.extend(search_naver_api(k, "blog"))
                all_r.extend(search_naver_api(k, "cafearticle"))
                # 구글/유튜브 수집 [cite: 333-334]
                res = requests.post("https://google.serper.dev/search", headers={'X-API-KEY': serper_key}, json={"q": f"{k} 후기", "num": 10, "gl": "kr", "hl": "ko"}).json()
                for r in res.get('organic', []):
                    tag = get_media_tag(r.get('link', ''))
                    all_r.append(f"{tag} {r.get('title')}: {r.get('snippet')}")
            st.session_state['consumer_data'] = all_r
            st.session_state['consumer_analysis'] = run_ai_analysis("\n".join(all_r), "consumer")
            _ = st.rerun()
    st.markdown(st.session_state['consumer_analysis'])

elif menu == "3단계. 통합 전략 및 PDF":
    st.title("🧠 3단계. 최종 Victory Strategy 리포트")
    if st.button("🚀 최종 리포트 생성"):
        with st.spinner("데이터 통합 및 Gap 도출 중..."):
            comb = f"자사:{st.session_state['brand_analysis']}\n경쟁사:{st.session_state['comp_analysis']}\n소비자:{st.session_state['consumer_analysis']}"
            st.session_state['final_report'] = run_ai_analysis(comb, "final", st.session_state['brand_insight'], consumer_raw=str(st.session_state['consumer_data']))
            _ = st.rerun()
    
    if st.session_state['final_report']:
        st.markdown(st.session_state['final_report'])
        st.divider()
        pdf = PiecePDF()
        _ = pdf.write_safe("BRAND ANALYSIS", st.session_state['brand_analysis'])
        _ = pdf.write_safe("COMPETITOR ANALYSIS", st.session_state['comp_analysis'])
        _ = pdf.write_safe("CONSUMER RAW VOICE", st.session_state['consumer_analysis'])
        _ = pdf.write_safe("VICTORY STRATEGY master", st.session_state['final_report'])
        _ = st.download_button("📥 통합 리포트 PDF 다운로드 (One-Click)", data=bytes(pdf.output()), file_name="GapFinder_v21_5.pdf", mime="application/pdf")