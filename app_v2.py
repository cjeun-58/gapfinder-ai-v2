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
_ = st.set_page_config(page_title="GapFinder v2 (v24.4)", layout="wide")

states = ['brand_analysis', 'brand_insight', 'comp_analysis', 'consumer_data', 'consumer_analysis', 'final_report']
for key in states:
    if key not in st.session_state:
        st.session_state[key] = "" 

if 'consumer_data' not in st.session_state or not isinstance(st.session_state['consumer_data'], list):
    st.session_state['consumer_data'] = []

# --- 2. 사이드바 설정 ---
with st.sidebar:
    st.header("🔑 GapFinder v2 설정")
    gemini_key = st.text_input("1. Gemini API Key", type="password")
    serper_key = st.text_input("2. Serper API Key", type="password")
    
    st.divider()
    st.subheader("🇳 네이버 검색 API (선택)")
    nav_id = st.text_input("Naver Client ID")
    nav_pw = st.text_input("Naver Client Secret", type="password")
    
    _ = st.divider()
    menu = st.radio("분석 프로세스 단계", [
        "1단계. 브랜드 분석 (Thesis)", 
        "2단계. 경쟁사 분석 (Competitor)", 
        "3단계. 소비자 분석 (Evidence)", 
        "4단계. 통합 전략 리포트 (Synthesis)"
    ])

# --- 3. 유틸리티 함수 ---

def clean_for_pdf(text):
    """PDF 출력 시 폰트 충돌 방지 세척 [cite: 589-591]"""
    if not text: return ""
    text = str(text).replace('\u200b', '').replace('\ufeff', '').replace('|', ' ')
    return re.sub(r'[^\u0000-\u007f\uac00-\ud7af\x20-\x7E\s\n\.,!\?\(\)\[\]:;\"\'\-]', '', text)

def extract_all_content(files=None, url=""):
    """이미지/문서/웹 텍스트 추출 [cite: 755-758]"""
    text = ""
    if files:
        for f in files:
            try:
                if f.name.endswith(".pdf"): text += "\n".join([p.extract_text() for p in PdfReader(f).pages if p.extract_text()])
                elif f.name.endswith(".pptx"): text += "\n".join([s.text for slide in Presentation(f).slides for s in slide.shapes if hasattr(s, "text")])
                elif f.name.lower().endswith((".png", ".jpg", ".jpeg")):
                    text += f"\n[OCR 데이터: {f.name}]:\n" + pytesseract.image_to_string(Image.open(f), lang='kor+eng')
            except: pass
    if url:
        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            for s in soup(['script', 'style']): s.decompose()
            text += f"\n[참조 URL: {url}]\n{soup.get_text()[:4000]}"
        except: pass
    return text

def run_ai(data, step, insight="", brand_ctx="", consumer_raw=""):
    """Gap 분석 및 전략 도출 엔진 [cite: 414-417, 785-787]"""
    if not gemini_key: return "⚠️ API Key가 필요합니다."
    try:
        client = genai.Client(api_key=gemini_key)
        p_base = """인사말은 생략하고 15년 차 수석 전략 기획자의 전문적인 비즈니스 언어를 사용하세요. 
        분석 카테고리는 [기능 / 가격 / 서비스 / 디자인] 4대 체계를 반드시 준수하세요.\n\n"""
        
        prompts = {
            "brand": f"""{p_base}[Thesis] 자사 브랜드 분석:
            1. Value Opportunity Index (VOI): 현재 자산 중 시장 압도가 가능한 요소 2가지. [cite: 1581-1586]
            2. Purchase Deterrence Index (PDI): 잠재 고객 이탈 리스크 2가지와 구매 저해 지수(1-10점). [cite: 1587-1591]
            인사이트: {insight}""",
            
            "comp": f"""{p_base}[Competitor] 경쟁 우위 분석: 경쟁사들의 '언어의 영토'와 '전략적 사각지대'를 분석하세요. [cite: 1622-1640]
            자사({brand_ctx[:300]})가 시장 판도를 바꿀 수 있는 전략을 제언하세요.""",
            
            "consumer": f"""{p_base}[Evidence] 소비자 여론 분석: 소비자 보이스를 4대 카테고리로 분류하여, 
            기대치와 실체의 '불일치(Gap)'를 정량적으로 추론하세요. [cite: 182-212]""",
            
            "final": f"""{p_base}[Synthesis] Victory Strategy:
            1. Language Gap Matrix: 브랜드 보이스와 소비자 실체의 괴리 분석. [cite: 1575-1578]
            2. Strategic Foundations: VOI/PDI 통합 기반 리스크 극복 방향. [cite: 1716-1720]
            3. Target-Action Table: [타겟 / 페인포인트 / 킬러 카피 / 임팩트] 테이블 생성. [cite: 723-732, 1721-1724]
            4. 최종 결론: 시장 지배적 지위 확보를 위한 통합 전략 정의 (한 문장). [cite: 1726-1730]
            인사이트: {insight}\n데이터: {consumer_raw[:10000]}""" # [DATA_LIMIT] 데이터 증가 시 슬라이싱 확장
        }
        # [DATA_LIMIT] 100개 수집 시 str(data)[:20000]를 40000 이상으로 확장 권장
        res = client.models.generate_content(model="gemini-3-flash-preview", contents=prompts[step] + "\n\n데이터:\n" + str(data)[:25000])
        return res.text
    except Exception as e: return f"분석 오류: {e}"

# --- 4. PDF 클래스 ---

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

# --- 5. 단계별 실행 ---

if menu == "1단계. 브랜드 분석 (Thesis)":
    st.title("🏢 1단계. 브랜드 자산 및 리스크 분석")
    b_f = st.file_uploader("자사 자료 업로드", accept_multiple_files=True)
    b_u = st.text_input("자사 URL")
    st.session_state['brand_insight'] = st.text_area("💡 실무/운영 인사이트", value=st.session_state['brand_insight'] if st.session_state['brand_insight'] != "" else "")
    if st.button("브랜드 분석 시작"):
        with st.spinner("데이터 분석 중..."):
            st.session_state['brand_analysis'] = run_ai(extract_all_content(b_f, b_u), "brand", st.session_state['brand_insight'])
            _ = st.rerun()
    if st.session_state['brand_analysis']: st.markdown(st.session_state['brand_analysis'])

elif menu == "2단계. 경쟁사 분석 (Competitor)":
    st.title("⚔️ 2단계. 경쟁 구도 및 시장 사각지대 (최대 3개)")
    c_f = st.file_uploader("경쟁사 자료", accept_multiple_files=True)
    col1, col2, col3 = st.columns(3)
    with col1: c1n = st.text_input("경쟁사 1"); c1u = st.text_input("URL 1")
    with col2: c2n = st.text_input("경쟁사 2"); c2u = st.text_input("URL 2")
    with col3: c3n = st.text_input("경쟁사 3"); c3u = st.text_input("URL 3")
    if st.button("경쟁 분석 시작"):
        with st.spinner("틈새 분석 중..."):
            all_c = extract_all_content(c_f)
            for n, u in [(c1n, c1u), (c2n, c2u), (c3n, c3u)]:
                if n:
                    # [DATA_LIMIT] 경쟁사 리뷰 수집량 (현재 50, 최대 100까지 가능)
                    res = requests.post("https://google.serper.dev/search", headers={'X-API-KEY': serper_key}, json={"q": f"{n} 실사용 불만 후기", "num": 50, "gl": "kr", "hl": "ko"}).json()
                    all_c += f"\n[{n} 데이터]\n" + "\n".join([r.get('snippet', '') for r in res.get('organic', [])])
                    if u: all_c += extract_all_content(url=u)
            st.session_state['comp_analysis'] = run_ai(all_c, "comp", brand_ctx=st.session_state['brand_analysis'])
            _ = st.rerun()
    if st.session_state['comp_analysis']: st.markdown(st.session_state['comp_analysis'])

elif menu == "3단계. 소비자 분석 (Evidence)":
    st.title("👥 3단계. 소비자 보이스 정량 분류")
    kw = st.text_input("분석 키워드 입력", value="")
    if st.button("데이터 수집 및 분석 시작"):
        if not kw: st.warning("키워드를 입력해주세요.")
        else:
            with st.spinner("대량 데이터 수집 및 분류 중..."):
                all_r = []
                for k in [x.strip() for x in kw.split(",")]:
                    # [DATA_LIMIT] 소비자 리뷰 수집량 (현재 50, 최대 100까지 가능) 
                    res = requests.post("https://google.serper.dev/search", headers={'X-API-KEY': serper_key}, json={"q": f"{k}", "num": 50, "gl": "kr", "hl": "ko"}).json()
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
        col_c1, col_c2 = st.columns([2, 1])
        with col_c1:
            with st.expander(f"📝 원본 데이터 ({len(st.session_state['consumer_data'])}건)"):
                for line in st.session_state['consumer_data']: st.write(line)
        with col_c2:
            st.download_button(f"📥 에비던스 팩 다운로드", data="\n".join(st.session_state['consumer_data']), file_name="Evidence_Full.txt")

elif menu == "4단계. 통합 전략 리포트 (Synthesis)":
    st.title("🧠 4단계. 최종 Victory Strategy")
    if st.button("🚀 최종 리포트 생성"):
        with st.spinner("모든 Gap 연결 중..."):
            comb = f"자사:{st.session_state['brand_analysis']}\n경쟁:{st.session_state['comp_analysis']}\n소비자:{st.session_state['consumer_analysis']}"
            st.session_state['final_report'] = run_ai(comb, "final", st.session_state['brand_insight'], consumer_raw=str(st.session_state['consumer_data']))
            _ = st.rerun()
    if st.session_state['final_report']:
        st.markdown(st.session_state['final_report'])
        st.divider()
        pdf = SafePDF()
        pdf.write_section("1. STRATEGIC THESIS", st.session_state['brand_analysis'])
        pdf.write_section("2. COMPETITIVE GAP", st.session_state['comp_analysis'])
        pdf.write_section("3. CONSUMER INSIGHT", st.session_state['consumer_analysis'])
        pdf.write_section("4. VICTORY STRATEGY v24.4", st.session_state['final_report'])
        st.download_button("📥 통합 리포트 PDF 다운로드", data=bytes(pdf.output()), file_name="GapFinder_v24_Final.pdf", mime="application/pdf")
