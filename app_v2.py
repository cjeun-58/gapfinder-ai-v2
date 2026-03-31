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
_ = st.set_page_config(page_title="GapFinder v2 (v23.2)", layout="wide")

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
    """PDF 출력 시 유니코드 에러 방지 [cite: 589-591]"""
    if not text: return ""
    text = str(text).replace('\u200b', '').replace('\ufeff', '').replace('|', ' ')
    clean = re.sub(r'[^\u0000-\u007f\uac00-\ud7af\u3130-\u318f\n\s\.,!\?\(\)\[\]:;\"\'\-]', '', text)
    return clean

def extract_all_content(files=None, url=""):
    """이미지/문서/웹 텍스트 추출 [cite: 755-758]"""
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
                    text += f"\n[이미지 {f.name} 데이터]:\n" + pytesseract.image_to_string(img, lang='kor+eng')
            except: pass
    if url:
        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            for s in soup(['script', 'style']): s.decompose()
            text += f"\nhttps://help.hancom.com/hoffice/multi/ko_kr/hwp/insert/cross_reference/cross_reference%28endnotes%29.htm\n{soup.get_text()[:3000]}"
        except: pass
    return text

def run_ai(data, step, insight="", brand_ctx="", consumer_raw=""):
    """균형 잡힌 시각을 가진 수석 기획자 페르소나 [cite: 414-417, 785-787]"""
    if not gemini_key: return "⚠️ Gemini API Key가 필요합니다."
    try:
        client = genai.Client(api_key=gemini_key)
        p_base = """인사말은 생략하고 15년 차 수석 전략 기획자의 객관적이고 균형 잡힌 전문 용어를 사용하세요. 
        브랜드의 강점(Asset)과 약점(Risk)을 동시에 분석하여 시장 내 실질적인 기회를 도출해야 합니다.
        모든 데이터는 [기능 / 가격 / 서비스 / 디자인] 카테고리로 분류하세요.\n\n"""
        
        prompts = {
            "brand": f"""{p_base}[Thesis] 자사 분석: 
            1. 가치 기회 지수(VOI, 1-10점): 시장을 압도할 핵심 자산 2가지와 점수.
            2. 구매 저해 지수(PDI, 1-10점): 현재 성장을 가로막는 리스크 2가지와 점수.
            인사이트: {insight}""",
            
            "comp": f"""{p_base}[Competitor] 경쟁사 분석: 경쟁사가 시장을 점유한 방식과 그들의 한계를 대조 분석하세요. 
            자사({brand_ctx[:200]})의 VOI가 경쟁사의 약점을 어떻게 공략할 수 있는지 도출하세요.""",
            
            "consumer": f"""{p_base}[Evidence] 소비자 분석: 후기 데이터를 [긍정적 열광 포인트]와 [부정적 불만 사항]으로 5:5 비중으로 분류하세요. 
            카테고리별(기능/가격/서비스/디자인) 만족도 현황을 수치화하여 제시하세요.""",
            
            "final": f"""{p_base}[Synthesis] Victory Strategy: 
            1. Value-Risk 매트릭스 (자사의 강점과 약점 대조표)
            2. 전략적 카피 테이블: [강점 강화형(Amplify) 카피]와 [약점 보완형(Solve) 카피] 제안
            3. 전무님 보고용 최종 통합 전략 (한 문장 정의)\n인사이트: {insight}\n데이터: {consumer_raw[:5000]}"""
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
        self.multi_cell(170, 7, txt=clean_for_pdf(content))

# --- 5. UI 단계별 실행 (쿼터 가드 적용) ---

if menu == "1단계. 브랜드 분석 (Thesis)":
    st.title("🏢 1단계. 브랜드 가치 및 리스크 분석 (VOI & PDI)")
    b_f = st.file_uploader("자사 자료 업로드 (이미지/문서)", accept_multiple_files=True)
    b_u = st.text_input("자사 URL")
    st.session_state['brand_insight'] = st.text_area("💡 실무 운영 인사이트", value=st.session_state['brand_insight'])
    
    btn_label = "객관적 분석 시작" if not st.session_state['brand_analysis'] else "다시 분석하기 (쿼터 소진)"
    if st.button(btn_label):
        with st.spinner("가치와 리스크를 균형 있게 분석 중..."):
            st.session_state['brand_analysis'] = run_ai(extract_all_content(b_f, b_u), "brand", st.session_state['brand_insight'])
            _ = st.rerun()
    if st.session_state['brand_analysis']: st.markdown(st.session_state['brand_analysis'])

elif menu == "2단계. 경쟁사 분석 (Competitor)":
    st.title("⚔️ 2단계. 경쟁사 대조 및 틈새 분석")
    c_f = st.file_uploader("경쟁사 자료 업로드", accept_multiple_files=True)
    col1, col2 = st.columns([1, 2])
    with col1: c1n = st.text_input("경쟁사 1"); c2n = st.text_input("경쟁사 2")
    with col2: c1u = st.text_input("경쟁사 1 URL"); c2u = st.text_input("경쟁사 2 URL")
    
    btn_label = "경쟁 분석 시작" if not st.session_state['comp_analysis'] else "다시 분석하기"
    if st.button(btn_label):
        with st.spinner("경쟁 우위 지점 탐색 중..."):
            all_c = extract_all_content(c_f)
            for n, u in [(c1n, c1u), (c2n, c2u)]:
                if n:
                    res = requests.post("https://google.serper.dev/search", headers={'X-API-KEY': serper_key}, json={"q": f"{n} 실사용 장단점", "gl": "kr", "hl": "ko"}).json()
                    all_c += f"\n[{n}]\n" + "\n".join([r.get('snippet', '') for r in res.get('organic', [])])
                    if u: all_c += extract_all_content(url=u)
            st.session_state['comp_analysis'] = run_ai(all_c, "comp", brand_ctx=st.session_state['brand_analysis'])
            _ = st.rerun()
    if st.session_state['comp_analysis']: st.markdown(st.session_state['comp_analysis'])

elif menu == "3단계. 소비자 분석 (Evidence)":
    st.title("👥 3단계. 소비자 긍/부정 정량 분석")
    kw = st.text_input("분석 키워드 (쉼표 구분)", value="애사비 장점 단점")
    
    btn_label = "데이터 분석 시작" if not st.session_state['consumer_analysis'] else "데이터 다시 수집"
    if st.button(btn_label):
        with st.spinner("긍/부정 보이스 분류 중..."):
            all_r = []
            for k in [x.strip() for x in kw.split(",")]:
                if k:
                    res = requests.post("https://google.serper.dev/search", headers={'X-API-KEY': serper_key}, json={"q": f"{k}", "num": 15}).json()
                    for r in res.get('organic', []):
                        tag = "[🔴유튜브]" if "youtube" in r.get('link', '') else "[🔵네이버]" if "naver" in r.get('link', '') else "[⚪기타]"
                        all_r.append(f"{tag} {r.get('title')}: {r.get('snippet')}")
            if all_r:
                st.session_state['consumer_data'] = all_r
                st.session_state['consumer_analysis'] = run_ai("\n".join(all_r), "consumer")
                _ = st.rerun()
    
    if st.session_state['consumer_analysis']: 
        st.markdown(st.session_state['consumer_analysis'])
        st.divider()
        with st.expander("원본 데이터 확인"):
            for line in st.session_state['consumer_data']: st.write(line)

elif menu == "4단계. 통합 전략 리포트 (Synthesis)":
    st.title("🧠 4단계. 최종 Victory Strategy 리포트 (Balanced)")
    if st.button("🚀 최종 전략 리포트 생성"):
        with st.spinner("가치와 기회를 합성 중..."):
            comb = f"자사:{st.session_state['brand_analysis']}\n경쟁사:{st.session_state['comp_analysis']}\n소비자:{st.session_state['consumer_analysis']}"
            st.session_state['final_report'] = run_ai(comb, "final", st.session_state['brand_insight'], consumer_raw=str(st.session_state['consumer_data']))
            _ = st.rerun()
    
    if st.session_state['final_report']:
        st.markdown(st.session_state['final_report'])
        st.divider()
        pdf = SafePDF()
        pdf.write_section("1. BRAND ASSETS & RISKS", st.session_state['brand_analysis'])
        pdf.write_section("2. COMPETITIVE ADVANTAGE", st.session_state['comp_analysis'])
        pdf.write_section("3. CONSUMER SENTIMENT", st.session_state['consumer_analysis'])
        pdf.write_section("4. VICTORY STRATEGY v23.2", st.session_state['final_report'])
        st.download_button("📥 통합 리포트 PDF 다운로드", data=bytes(pdf.output()), file_name="GapFinder_v23_Balanced.pdf", mime="application/pdf")
