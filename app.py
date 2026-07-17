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
    df_use_total = pd.read_csv('df_use_total.csv')
    df_center = pd.read_csv('df_center.csv')
    with open('seoul_gu.json', encoding='utf-8') as f:
        seoul_geo = json.load(f)
    return df_use_total, df_center, seoul_geo

df_use_total, df_center, seoul_geo = load_data()

# 구별 인력 총합 데이터 정제
df_center_agg = (
    df_center.groupby('시군구명')[['의사인원수', '간호사인원수', '사회복지사인원수']]
    .sum().reset_index()
)

# 인력 부족 자치구 계산 logic
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

# --- 상단 헤더 및 전체 요약 지표 ---
st.title("🧠 서울시 치매안심센터 현황 대시보드")

c1, c2, c3, c4 = st.columns(4)
c1.metric("총 추정치매환자수", f"{df_use_total['추정치매환자수'].sum():,.0f}명")
c2.metric("총 치매안심센터 수", f"{df_center['치매센터명'].nunique()}개")
c3.metric("총 의사 수", f"{df_center['의사인원수'].sum():,.0f}명")
c4.metric("총 간호사 수", f"{df_center['간호사인원수'].sum():,.0f}명")

st.markdown("---")

# --- 사이드바 조회 설정 ---
st.sidebar.header("🔍 조회 설정")
gu_options = ['전체'] + sorted(df_use_total['시군구'].unique().tolist())
selected_gu_sidebar = st.sidebar.selectbox("자치구 선택", gu_options)
resource_type = st.sidebar.radio("인력 지표 선택", ['의사인원수', '간호사인원수', '사회복지사인원수'])

# --- 지도 데이터 및 스타일 세팅 ---
patient_dict = df_use_total.set_index('시군구')['추정치매환자수'].to_dict()
vmin, vmax = min(patient_dict.values()), max(patient_dict.values())
colormap = cm.LinearColormap(colors=['#1a3636', '#00b4d8', '#00f5d4'], vmin=vmin, vmax=vmax)
colormap.caption = '추정치매환자수 밀도'

# 지도 초기화 (Dark Matter 그래픽 모드)
# ---------------- 지도 초기화 (흰 배경, 서울 자치구만 표시) ----------------
m = folium.Map(
    location=[37.5665, 126.9780],
    zoom_start=11,
    min_zoom=11,
    max_zoom=11,
    tiles=None,          # ← 기본 지도 타일(도로/지명 등) 없이 빈 캔버스
    zoom_control=False,
    scrollWheelZoom=False,
    dragging=False,
    doubleClickZoom=False,
    touchZoom=False,
    keyboard=False
)

# 배경을 확실히 흰색으로 고정
m.get_root().html.add_child(folium.Element(
    "<style>.leaflet-container{background:#ffffff !important;}</style>"
))

# 폴리곤 스타일 및 바인딩
def style_function(feature):
    gu = feature['properties']['name']
    val = patient_dict.get(gu, 0)
    is_selected = (gu == selected_gu_sidebar)
    return {
        'fillColor': colormap(val),
        'color': '#7b1fa2' if is_selected else '#999999',
        'weight': 3 if is_selected else 1,
        'fillOpacity': 0.9 if is_selected else 0.85,
    }

geo_layer = folium.GeoJson(
    seoul_geo,
    style_function=style_function,
    highlight_function=lambda x: {'weight': 3, 'color': '#7b1fa2', 'fillOpacity': 0.95},
    tooltip=folium.GeoJsonTooltip(fields=['name'], aliases=[''], labels=False, sticky=True),
)
geo_layer.add_to(m)
# colormap.add_to(m)  ← 삭제: 기본 범례(오른쪽 위) 표시 안 함

# 자치구명 라벨 추가
gu_centroids = {}
for feature in seoul_geo['features']:
    gu_name = feature['properties']['name']
    centroid = shape(feature['geometry']).centroid
    gu_centroids[gu_name] = (centroid.y, centroid.x)

label_html = (
        '<div style="font-size:11px; font-weight:700; color:#222222; text-align:center;'
        'text-shadow: 1px 1px 2px #fff, -1px -1px 2px #fff, 1px -1px 2px #fff, -1px 1px 2px #fff;">'
        + gu_name + '</div>'
    )
    folium.Marker(
        location=[centroid.y, centroid.x],
        icon=folium.DivIcon(icon_size=(80, 20), icon_anchor=(40, 10), html=label_html)
    ).add_to(m)

# 인력 부족 자치구 시각화 테두리 (네온 레드)
overlap_geo = {"type": "FeatureCollection",
               "features": [f for f in seoul_geo['features'] if f['properties']['name'] in overlap_any]}
folium.GeoJson(
    overlap_geo,
    style_function=lambda x: {
        'fillColor': '#ff4d4d', 
        'fillOpacity': 0.1,      
        'color': '#ff4d4d',       
        'weight': 3, 
        'dashArray': '4, 4'
    },
    tooltip=folium.GeoJsonTooltip(fields=['name'], aliases=[''], labels=False, sticky=True),
    highlight_function=lambda x: {'weight': 3, 'fillOpacity': 0.3}
).add_to(m)

# 인력 부족 뱃지 추가
for gu_name in overlap_any:
    if gu_name not in gu_centroids:
        continue
    lat, lon = gu_centroids[gu_name]
    reason_text = '·'.join(gu_reasons[gu_name]) + ' 부족'
    
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


# ---------------- [추가 구현 1] 지도 바로 위에 렌더링될 그래픽 범례 ----------------
legend_col1, legend_col2 = st.columns([2, 1])

with legend_col1:
    st.subheader("🗺️ 서울시 자치구별 치매 안심 지형도")
with legend_col2:
    # 예쁜 가로형 인포그래픽 범례 컴포넌트 생성
    st.markdown(
        """
        <div style="display: flex; gap: 15px; justify-content: flex-end; align-items: center; padding-top: 10px;">
            <div style="display: flex; align-items: center; gap: 6px;">
                <span style="display: inline-block; width: 14px; height: 14px; background: linear-gradient(90deg, #1a3636, #00f5d4); border-radius: 3px;"></span>
                <span style="font-size: 12px; font-weight: 500; color: #bbb;">치매환자수 밀도</span>
            </div>
            <div style="display: flex; align-items: center; gap: 6px;">
                <span style="display: inline-block; width: 14px; height: 14px; border: 2px dashed #ff4d4d; background: rgba(255, 77, 77, 0.15); border-radius: 3px;"></span>
                <span style="font-size: 12px; font-weight: 500; color: #ff9999;">인력 부족 위기 구</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ---------------- [추가 구현 2] 2분할 레이아웃 적용 (왼쪽: 지도, 오른쪽: 클릭 시 실시간 수치 시각화) ----------------
map_layout_left, data_layout_right = st.columns([7, 4])

# ---------------- 왼쪽 하단 범례 (추정치매환자수 밀도) ----------------
legend_html_bottomleft = f'''
<div style="position: fixed; bottom: 40px; left: 40px; z-index:9999;
            background-color:white; padding:10px 14px; border:1px solid #ddd; border-radius:8px;
            box-shadow:0 2px 6px rgba(0,0,0,0.15); font-size:12px;">
    <div style="font-weight:bold; margin-bottom:6px;">추정치매환자수 밀도</div>
    <div style="width:160px; height:12px; border-radius:4px;
                background: linear-gradient(90deg, {colormap.colors[0]}, {colormap.colors[len(colormap.colors)//2]}, {colormap.colors[-1]});">
    </div>
    <div style="display:flex; justify-content:space-between; margin-top:3px; color:#666;">
        <span>{vmin:,.0f}</span><span>{vmax:,.0f}</span>
    </div>
</div>
'''
m.get_root().html.add_child(folium.Element(legend_html_bottomleft))

with map_layout_left:
    # 인터랙티브 지도 렌더링
    map_data = st_folium(m, width=750, height=580)

# 클릭 이벤트를 통해 활성화할 자치구 추출
clicked_gu = None
if map_data and map_data.get('last_object_clicked_tooltip'):
    clicked_gu = map_data['last_object_clicked_tooltip'].strip()

# 클릭한 자치구가 최우선, 없다면 사이드바 선택 적용, 둘 다 없으면 기본값 None
final_gu = clicked_gu if clicked_gu else (selected_gu_sidebar if selected_gu_sidebar != '전체' else None)


# ---------------- [추가 구현 3] 우측 사이드 패널에 자치구별 수치 시각화 데이터 바인딩 ----------------
with data_layout_right:
    if final_gu:
        st.markdown(f"### 📍 **{final_gu}** 실시간 치매 지표")
        
        # 환자 통계 데이터 로드 및 시각화
        row = df_use_total[df_use_total['시군구'] == final_gu]
        if not row.empty:
            r = row.iloc[0]
            
            # 1. 환자 지표 카드 형태 시각화
            st.markdown(
                f"""
                <div style="background-color: #1e222b; padding: 15px; border-radius: 10px; border-left: 5px solid #00f5d4; margin-bottom: 15px;">
                    <p style="margin: 0; font-size: 12px; color: #888;">추정 치매 환자수</p>
                    <h2 style="margin: 5px 0 0 0; color: #00f5d4;">{r['추정치매환자수']:,.0f} 명</h2>
                    <p style="margin: 5px 0 0 0; font-size: 12px; color: #ccc;">전체 노인 인구 {r['노인인구수']:,.0f}명 중 약 <b>{r['추정치매환자유병률']}%</b> 유병률</p>
                </div>
                """,
                unsafe_allow_html=True
            )

        # 2. 인력 데이터 로드 및 프로그레스 바 형태의 시각화
        st.markdown("🧑‍⚕️ **지정 자치구 의료 인력 현황**")
        centers = df_center[df_center['시군구명'] == final_gu]
        
        if not centers.empty:
            total_doc = centers['의사인원수'].sum()
            total_nurse = centers['간호사인원수'].sum()
            total_social = centers['사회복지사인원수'].sum()
            
            # 시각적인 인력 프로그레스 막대 바 그래프 구현 (서울시 최대값 기준 비교용 비율 환산)
            max_doc = df_center_agg['의사인원수'].max()
            max_nurse = df_center_agg['간호사인원수'].max()
            max_social = df_center_agg['사회복지사인원수'].max()

            doc_pct = min(float(total_doc / max_doc), 1.0) if max_doc else 0.0
            nurse_pct = min(float(total_nurse / max_nurse), 1.0) if max_nurse else 0.0
            social_pct = min(float(total_social / max_social), 1.0) if max_social else 0.0

            st.write(f"의사 수: {total_doc}명")
            st.progress(doc_pct)
            st.write(f"간호사 수: {total_nurse}명")
            st.progress(nurse_pct)
            st.write(f"사회복지사 수: {total_social}명")
            st.progress(social_pct)
            
            # 등록된 안심센터 정보 미니 표
            st.write("")
            st.caption("🏢 관내 등록 치매안심센터 세부 인력")
            st.dataframe(
                centers[['치매센터명', '의사인원수', '간호사인원수', '사회복지사인원수']],
                use_container_width=True, hide_index=True
            )
        else:
            st.info("이 구에는 등록된 치매안심센터 정보가 없어요.")
            
        # 만약 인력 위기 구인 경우 경고 메시지 플로팅
        if final_gu in overlap_any:
            st.error(f"⚠️ **{final_gu}**는 치매 환자수에 비해 **{'·'.join(gu_reasons[final_gu])}** 인력이 현저히 부족합니다.")
            
    else:
        # 미클릭 상태 디자인 가이드 멘트
        st.markdown(
            """
            <div style="border: 2px dashed #444; border-radius: 10px; padding: 40px 20px; text-align: center; margin-top: 50px;">
                <p style="font-size: 40px; margin: 0;">🖱️</p>
                <h4 style="color: #bbb; margin-top: 15px;">자치구를 클릭해 보세요!</h4>
                <p style="font-size: 13px; color: #777; margin: 5px 0 0 0;">지도에서 보고 싶은 자치구를 클릭하면 실시간 상세 정보 시각화 그래프가 이 영역에 나타납니다.</p>
            </div>
            """,
            unsafe_allow_html=True
        )

# --- [여기 아래부터는 기존 하단 데이터 테이블 영역이 그대로 배치됩니다] ---
st.markdown("---")
st.subheader("📊 치매안심센터 인력 상위 4 / 하위 4 자치구")

tab1, tab2, tab3 = st.tabs(["의사수", "간호사수", "사회복지사수"])

def show_rank_table(col_name):
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"**🔼 {col_name} 상위 4개 구**")
        top4_df = (
            df_center_agg.sort_values(col_name, ascending=False)
            .head(4)[['시군구명', col_name]]
            .reset_index(drop=True)
        )
        top4_df.index = top4_df.index + 1
        st.dataframe(top4_df, use_container_width=True)

    with col2:
        st.markdown(f"**🔽 {col_name} 하위 4개 구**")
        bottom4_df = (
            df_center_agg.sort_values(col_name)
            .head(4)[['시군구명', col_name]]
            .reset_index(drop=True)
        )
        bottom4_df.index = bottom4_df.index + 1
        st.dataframe(bottom4_df, use_container_width=True)

with tab1:
    show_rank_table('의사인원수')

with tab2:
    show_rank_table('간호사인원수')

with tab3:
    show_rank_table('사회복지사인원수')

st.markdown("---")
st.subheader("⚠️ 환자수 상위 4개 구 중 인력 부족 구")
if overlap_any:
    overlap_df = pd.DataFrame([
        {'시군구': gu, '부족 인력': '·'.join(gu_reasons[gu])}
        for gu in sorted(overlap_any)
    ])
    st.dataframe(overlap_df, use_container_width=True, hide_index=True)
else:
    st.info("해당하는 자치구가 없습니다.")
