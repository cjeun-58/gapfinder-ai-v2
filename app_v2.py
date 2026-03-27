import streamlit as st
from google import genai
import pandas as pd
from PyPDF2 import PdfReader
from pptx import Presentation
import requests
from bs4 import BeautifulSoup
from fpdf import FPDF
import io
import os
import re
from PIL import Image
import pytesseract

# --- 1. 페이지 설정 및 데이터 초기화 ---
_ = st.set_page_config(page_title="GapFinder v2 (v22.1)", layout="wide")

states = ['brand_analysis', 'brand_insight', 'comp_analysis', 'consumer_data', 'consumer_analysis', 'final_report']
for key in states:
    if key not in st.session_state:
        st.session_state[key] = "" if 'analysis' in key or 'report' in key else []
if 'brand_insight' not in st.session_state:
    st.session_state['brand_insight'] = ""

# --- 2. 사이드바 (API 설정 및 현황) ---
with st.sidebar:
    st.header("🔑 v2 서비스 설정")
    gemini_key = st.text_input("1. Gemini API Key", type="password")
    serper_key = st.text_input("2. Serper API Key", type="password")
    
    st.divider()
    st.subheader("🇳 네이버 검색 API (선택)")
    naver_id = st.text_input("Naver Client ID")
    naver_secret = st.text_input("Naver Client Secret", type="password")
    
    _ = st.divider()
    menu = st.radio("전략 수립 단계", [
        "1단계. 브랜드 분석 (Thesis)", 
        "2단계. 경쟁사 분석 (Competitor)", 
        "3단계. 소비자 분석 (Evidence)", 
        "4단계. 통합 전략 리포트 (Synthesis)"
    ])
    
    _ = st.divider()
    st.subheader("📊 실시간 분석 현황")
    st.write(f"🏢 브랜드: {'✅' if st.session_state['brand_analysis'] else '❌'}")
    st.write(f"⚔️ 경쟁사: {'✅' if st.session_state['comp_analysis'] else '❌'}")
    st.write(f"👥 소비자: {'✅' if st.session_state['consumer_analysis'] else '❌'}")

# --- 3. 핵심 엔진 (OCR & PDF 안전 로직) ---

def clean_for_pdf(text):
    """PDF 유니코드 에러 방지용 강력 세척 로직"""
    if not text: return ""
    text = str(text).replace('\u200b', '').replace('\ufeff', '').replace('|', ' ')
    # 한글, 영문, 숫자, 기본 문장부호만 남기고 이모지 등 제거
    clean = re.sub(r'[^\u0000-\u007f\uac00-\ud7af\u3130-\u318f\n\s\.,!\?\(\)\[\]:;\"\'\-]', '', text)
    return clean

def extract_all_content(files=None, url=""):
    """이미지(OCR), 문서, 웹 텍스트 추출"""
    text = ""
    if files:
        for f in files:
            try:
                if f.name.endswith(".pdf"):
                    text += "\n".join([p.extract_text() for p in PdfReader(f).pages if p.extract_text()])
                elif f.name.endswith(".pptx"):
                    text += "\n".join([s.text for slide in Presentation(f).slides for s in slide.shapes if hasattr(s, "text")])
                elif f.name.lower().endswith((".png", ".jpg", ".jpeg")):
                    img = Image.open(f)
                    text += f"\n[이미지 {f.name} OCR 데이터]:\n" + pytesseract.image_to_string(img, lang='kor+eng')
            except: pass
    if url:
        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            for s in soup(['script', 'style']): s.decompose()
            text += f"\nhttps://help.hancom.com/hoffice/multi/ko_kr/hwp/insert/cross_reference/cross_reference%28endnotes%29.htm\n{soup.get_text()[:3000]}"
        except: pass
    return text

def search_naver(query, target="blog"):
    """네이버 공식 API 연동"""
    if not naver_id or not naver_secret: return []
    headers = {"X-Naver-Client-Id": naver_id, "X-Naver-Client-Secret": naver_secret}
    url = f"https://openapi.naver.com/v1/search/{target}.json?query={query}&display=15"
    try:
        res = requests.get(url, headers=headers).json()
        tag = "[🟢네이버 블로그]" if target == "blog" else "[🔵네이버 카페]"
        return [f"{tag} {i['title']}: {i['description']}" for i in res.get('items', [])]
    except: return []

def run_ai(data, step, insight="", brand_ctx="", consumer_raw=""):
    """'짱'의 시각을 반영한 필승 전략 엔진"""
    if not gemini_key: return "⚠️ Gemini API Key가 필요합니다."
    if not data or len(str(data).strip()) < 10: return "⚠️ 분석할 재료가 부족합니다."
    try:
        client = genai.Client(api_key=gemini_key)
        p_base = "인사말 생략. 광고 기획 총괄자로서 리스트 형식으로 분석하세요.\n\n"
        prompts = {
            "brand": f"{p_base}[Thesis] 자사 브랜드 분석. 강점 및 소비자 소구 언어 분석. 인사이트: {insight}",
            "comp": f"{p_base}[Competitor] 입력된 경쟁사만 분석. 자사({brand_ctx[:200]})와 대비하여 비어 있는 White Space 발굴.",
            "consumer": f"{p_base}[Evidence] 소비자 데이터 분석. 날것의 페인포인트 도출.",
            "final": f"{p_base}[Victory Strategy v6.5]\n1. 브랜드 vs 소비자 언어 Gap 분석 (워딩 대조)\n2. 경쟁사 대비 White Space\n3. 타겟별 필승 광고 카피\n4. 최종 결론: 선언적 필승 전략 한 문장\n인사이트: {insight}\n데이터: {consumer_raw[:5000]}"
        }
        res = client.models.generate_content(model="gemini-3-flash-preview", contents=prompts[step] + "\n\n데이터:\n" + str(data)[:12000])
        return res.text
    except Exception as e: return f"분석 오류: {e}"

# --- 4. 무결점 PDF 클래스 ---

class SafePDF(FPDF):
    def __init__(self):
        super().__init__()
        f_reg, f_bold = "NanumGothic.ttf", "NanumGothicBold.ttf"
        if os.path.exists(f_reg):
            self.add_font('NG', '', f_reg); self.add_font('NG', 'B', f_bold); self.fn = 'NG'
        else: self.fn = 'Arial'
        _ = self.set_auto_page_break(auto=True, margin=20)
        _ = self.set_margins(20, 20, 20)

    def write_section(self, title, content):
        if not content: return
        self.add_page()
        self.set_font(self.fn, 'B', 16); self.set_text_color(0, 51, 102)
        self.cell(170, 15, txt=title, ln=True, align='C'); self.ln(5)
        self.set_font(self.fn, '', 10.5); self.set_text_color(50, 50, 50)
        # 강력 세척 후 출력하여 인코딩 에러 원천 차단
        self.multi_cell(170, 7, txt=clean_for_pdf(content))

# --- 5. UI 단계별 실행 ---

if menu == "1단계. 브랜드 분석 (Thesis)":
    st.title("🏢 1단계. 브랜드 분석 (문서/이미지/URL)")
    b_f = st.file_uploader("자사 자료 (PNG, JPG, PDF, PPTX)", accept_multiple_files=True, key="b_files")
    b_u = st.text_input("자사 URL")
    st.session_state['brand_insight'] = st.text_area("💡 운영 인사이트", value=st.session_state['brand_insight'])
    if st.button("브랜드 분석 시작"):
        with st.spinner("데이터 추출 중..."):
            st.session_state['brand_analysis'] = run_ai(extract_all_content(b_f, b_u), "brand", st.session_state['brand_insight'])
            _ = st.rerun()
    if st.session_state['brand_analysis']: st.markdown(st.session_state['brand_analysis'])

elif menu == "2단계. 경쟁사 분석 (Competitor)":
    st.title("⚔️ 2단계. 경쟁사 정밀 분석 (문서/이미지/URL)")
    c_f = st.file_uploader("경쟁사 자료 (PNG, JPG, PDF, PPTX)", accept_multiple_files=True, key="c_files")
    col1, col2 = st.columns([1, 2])
    with col1: c1n = st.text_input("경쟁사 1"); c2n = st.text_input("경쟁사 2"); c3n = st.text_input("경쟁사 3")
    with col2: c1u = st.text_input("경쟁사 1 URL"); c2u = st.text_input("경쟁사 2 URL"); c3u = st.text_input("경쟁사 3 URL")
    if st.button("경쟁사 분석 시작"):
        with st.spinner("경쟁사 데이터 수집 중..."):
            all_c = extract_all_content(c_f)
            for n, u in [(c1n, c1u), (c2n, c2u), (c3n, c3u)]:
                if n:
                    res = requests.post("https://google.serper.dev/search", headers={'X-API-KEY': serper_key}, json={"q": f"{n} 특징 소구점", "gl": "kr", "hl": "ko"}).json()
                    all_c += f"\n[{n}]\n" + "\n".join([r.get('snippet', '') for r in res.get('organic', [])])
                    if u: all_c += extract_all_content(url=u)
            st.session_state['comp_analysis'] = run_ai(all_c, "comp", brand_ctx=st.session_state['brand_analysis'])
            _ = st.rerun()
    if st.session_state['comp_analysis']: st.markdown(st.session_state['comp_analysis'])

elif menu == "3단계. 소비자 분석 (Evidence)":
    st.title("👥 3단계. 네이버 & 구글 통합 소비자 보이스")
    kw = st.text_input("분석 키워드 (쉼표 구분)", value="애사비, 애플사이다비니거")
    if st.button("데이터 수집 시작"):
        with st.spinner("멀티 채널 수집 중..."):
            all_r = []
            for k in [x.strip() for x in kw.split(",")]:
                if k:
                    all_r.extend(search_naver(k, "blog"))
                    all_r.extend(search_naver(k, "cafearticle"))
                    res = requests.post("https://google.serper.dev/search", headers={'X-API-KEY': serper_key}, json={"q": f"{k} 후기 단점", "num": 10, "gl": "kr", "hl": "ko"}).json()
                    for r in res.get('organic', []):
                        tag = "[🔴유튜브]" if "youtube" in r.get('link', '') else "[⚪구글/기타]"
                        all_r.append(f"{tag} {r.get('title')}: {r.get('snippet')}")
            if all_r:
                st.session_state['consumer_data'] = all_r
                st.session_state['consumer_analysis'] = run_ai("\n".join(all_r), "consumer")
                _ = st.rerun()
    if st.session_state['consumer_analysis']: 
        st.markdown(st.session_state['consumer_analysis'])
        st.divider()
        st.subheader("📝 수집된 원본 Raw 데이터 (Evidence)")
        with st.expander("원본 소리 펼쳐보기", expanded=True):
            for i, line in enumerate(st.session_state['consumer_data']):
                st.write(f"{i+1}. {line}")

elif menu == "4단계. 통합 전략 리포트 (Synthesis)":
    st.title("🧠 4단계. 최종 Victory Strategy 리포트")
    if st.button("🚀 최종 리포트 생성"):
        with st.spinner("전략 합성 중..."):
            comb = f"자사:{st.session_state['brand_analysis']}\n경쟁사:{st.session_state['comp_analysis']}\n소비자:{st.session_state['consumer_analysis']}"
            st.session_state['final_report'] = run_ai(comb, "final", st.session_state['brand_insight'], consumer_raw=str(st.session_state['consumer_data']))
            _ = st.rerun()
    
    if st.session_state['final_report']:
        st.markdown(st.session_state['final_report'])
        st.divider()
        pdf = SafePDF()
        pdf.write_section("1. BRAND ANALYSIS", st.session_state['brand_analysis'])
        pdf.write_section("2. COMPETITOR ANALYSIS", st.session_state['comp_analysis'])
        pdf.write_section("3. CONSUMER RAW VOICE", st.session_state['consumer_analysis'])
        pdf.write_section("4. VICTORY STRATEGY v6.5", st.session_state['final_report'])
        st.download_button("📥 통합 리포트 PDF 다운로드", data=bytes(pdf.output()), file_name="GapFinder_v2_Final.pdf", mime="application/pdf")
