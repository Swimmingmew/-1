import streamlit as st
import pandas as pd
import folium
import branca.colormap as cm
from streamlit_folium import st_folium
from shapely.geometry import shape
import json

st.set_page_config(page_title="서울시 치매안심센터 현황", layout="wide")

@st.cache_data
def load_data():
    # 데이터 로드는 기존과 동일
    df_use_total = pd.read_csv('df_use_total.csv')
    df_center = pd.read_csv('df_center.csv')
    with open('seoul_gu.json', encoding='utf-8') as f:
        seoul_geo = json.load(f)
    return df_use_total, df_center, seoul_geo

df_use_total, df_center, seoul_geo = load_data()

df_center_agg = (
    df_center.groupby('시군구명')[['의사인원수', '간호사인원수', '사회복지사인원수']]
    .sum().reset_index()
)

top4_patients_gu = set(df_use_total.sort_values('추정치매환자수', ascending=False).head(4)['시군구'])
bottom4 = {
    '의사': set(df_center_agg.sort_values('의사인원수').head(4)['시군구명']),
    '간호사': set(df_center_agg.sort_values('간호사인원수').head(4)['시군구명']),
    '사회복지사': set(df_center_agg.sort_values('사회복지사인원수').head(4)['시군구명']),
}
overlap_any = set()
gu_reasons = {}
for gu in top4_patients_gu:
    reasons = [k for k, v in bottom4.items() if gu in v]
    if reasons:
        overlap_any.add(gu)
        gu_reasons[gu] = reasons

st.title("🧠 서울시 치매안심센터 현황 대시보드")

c1, c2, c3, c4 = st.columns(4)
c1.metric("총 추정치매환자수", f"{df_use_total['추정치매환자수'].sum():,.0f}명")
c2.metric("총 치매안심센터 수", f"{df_center['치매센터명'].nunique()}개")
c3.metric("총 의사 수", f"{df_center['의사인원수'].sum():,.0f}명")
c4.metric("총 간호사 수", f"{df_center['간호사인원수'].sum():,.0f}명")

st.markdown("---")

st.sidebar.header("🔍 조회 설정")
gu_options = ['전체'] + sorted(df_use_total['시군구'].unique().tolist())
selected_gu_sidebar = st.sidebar.selectbox("자치구 선택", gu_options)
resource_type = st.sidebar.radio("인력 지표 선택", ['의사인원수', '간호사인원수', '사회복지사인원수'])

st.sidebar.markdown("---")
st.sidebar.markdown("**범례**")
st.sidebar.markdown("🟢 색상 진하기 : 추정치매환자수 밀도")
st.sidebar.markdown("🔴 붉은 테두리 : 환자수 대비 인력 부족")

# ---------------- [그래픽 변경 1] 컬러맵을 네온/사이버 펑크 그래픽 느낌으로 변경 ----------------
patient_dict = df_use_total.set_index('시군구')['추정치매환자수'].to_dict()
vmin, vmax = min(patient_dict.values()), max(patient_dict.values())
# 다크 모드에 어울리는 Cyan-Green 계열의 그래픽 컬러맵 적용
colormap = cm.LinearColormap(colors=['#1a3636', '#00b4d8', '#00f5d4'], vmin=vmin, vmax=vmax)
colormap.caption = '추정치매환자수 밀도'

# ---------------- [그래픽 변경 2] 지도 타일을 'CartoDB dark_matter'로 변경 및 초기 세팅 ----------------
m = folium.Map(
    location=[37.5665, 126.9780],
    zoom_start=11,
    min_zoom=11,
    max_zoom=11,
    tiles='CartoDB dark_matter', # 어두운 세련된 그래픽 맵으로 변경 (밝게 하고 싶다면 'CartoDB Positron')
    zoom_control=False,
    scrollWheelZoom=False,
    dragging=False,
    doubleClickZoom=False,
    touchZoom=False,
    keyboard=False
)

# ---------------- [그래픽 변경 3] 기본 행정구역 폴리곤 스타일 고도화 ----------------
def style_function(feature):
    gu = feature['properties']['name']
    val = patient_dict.get(gu, 0)
    is_selected = (gu == selected_gu_sidebar)
    
    return {
        'fillColor': colormap(val),
        'color': '#ffffff' if is_selected else '#444444', # 선택 시 화이트 네온 테두리
        'weight': 3 if is_selected else 1,
        'fillOpacity': 0.75 if is_selected else 0.55,      # 투명도 조절로 고급스러운 느낌 부여
    }

geo_layer = folium.GeoJson(
    seoul_geo,
    style_function=style_function,
    highlight_function=lambda x: {'weight': 3, 'color': '#ffffff', 'fillOpacity': 0.8}, # 마우스 오버 시 화이트 하이라이트
    tooltip=folium.GeoJsonTooltip(fields=['name'], aliases=[''], labels=False, sticky=True),
)
geo_layer.add_to(m)
colormap.add_to(m)

# ---------------- 구별 폴리곤 중심좌표 + 이름 라벨 그래픽 수정 ----------------
gu_centroids = {}
for feature in seoul_geo['features']:
    gu_name = feature['properties']['name']
    centroid = shape(feature['geometry']).centroid
    gu_centroids[gu_name] = (centroid.y, centroid.x)

    # 다크모드 배경에 맞게 글자색을 화이트(또는 연한 회색)로 변경하고 텍스트 그림자 고도화
    label_html = (
        '<div style="font-size:11px; font-weight:700; color:#ffffff; text-align:center;'
        'text-shadow: 0 0 4px #000, 0 0 4px #000;">'
        + gu_name + '</div>'
    )
    folium.Marker(
        location=[centroid.y, centroid.x],
        icon=folium.DivIcon(icon_size=(80, 20), icon_anchor=(40, 10), html=label_html)
    ).add_to(m)

# ---------------- [그래픽 변경 4] 경고 구역을 강렬한 네온 레드/오렌지 라인으로 변경 ----------------
overlap_geo = {"type": "FeatureCollection",
               "features": [f for f in seoul_geo['features'] if f['properties']['name'] in overlap_any]}
folium.GeoJson(
    overlap_geo,
    style_function=lambda x: {
        'fillColor': '#ff4d4d', 
        'fillOpacity': 0.15,      # 살짝 붉은 빛이 감돌게 변경
        'color': '#ff4d4d',       # 강렬한 네온 레드 테두리
        'weight': 3, 
        'dashArray': '4, 4'
    }
).add_to(m)

# ---------------- [그래픽 변경 5] 경고 라벨 뱃지 디자인 컴포넌트화 ----------------
for gu_name in overlap_any:
    if gu_name not in gu_centroids:
        continue
    lat, lon = gu_centroids[gu_name]
    reason_text = '·'.join(gu_reasons[gu_name]) + ' 부족'
    
    # 칙칙한 검은 뱃지 대신, 경고 의미를 담은 다크레드 그라디언트 보더 뱃지로 변경
    warn_html = (
        '<div style="background: rgba(255, 77, 77, 0.85); color: white; padding: 3px 8px; border-radius: 20px;'
        'font-size: 10px; font-weight: bold; white-space: nowrap; text-align: center;'
        'box-shadow: 0 0 8px rgba(255, 77, 77, 0.6); border: 1px solid #ff9999;">'
        f'⚠️ {reason_text}</div>'
    )
    folium.Marker(
        [lat + 0.011, lon],
        icon=folium.DivIcon(icon_size=(140, 24), icon_anchor=(70, 12), html=warn_html)
    ).add_to(m)

st.subheader("🗺️ 자치구별 치매현황 지도 (자치구를 클릭하면 하단에 상세정보가 표시돼요)")
map_data = st_folium(m, width=1100, height=650)

# (이후 정보 출력 및 랭킹 테이블 코드는 기존과 완벽히 동일하므로 생략합니다.)
# ... [기존 코드 유지] ...
