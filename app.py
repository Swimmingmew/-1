import streamlit as st
import pandas as pd
import folium
import branca.colormap as cm
from streamlit_folium import st_folium
from shapely.geometry import shape
import json
import numpy as np
import plotly.express as px

st.set_page_config(page_title="서울시 치매안심센터 현황", layout="wide")

@st.cache_data
def load_data():
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

st.title("🧠 서울시 치매환자 지원현황")

c1, c2, c3, c4 = st.columns(4)
c1.metric("총 추정치매환자수", f"{df_use_total['추정치매환자수'].sum():,.0f}명")
c2.metric("총 치매안심센터 수", f"{df_center['치매센터명'].nunique()}개")
c3.metric("총 의사 수", f"{df_center['의사인원수'].sum():,.0f}명")
c4.metric("총 간호사 수", f"{df_center['간호사인원수'].sum():,.0f}명")

st.markdown("---")

st.sidebar.header("🔍 조회 설정")
gu_options = ['전체'] + sorted(df_use_total['시군구'].unique().tolist())
selected_gu_sidebar = st.sidebar.selectbox("자치구 선택", gu_options)

patient_dict = df_use_total.set_index('시군구')['추정치매환자수'].to_dict()
vmin, vmax = min(patient_dict.values()), max(patient_dict.values())
colormap = cm.LinearColormap(colors=['#e0f7f5', '#00b4d8', '#1a3636'], vmin=vmin, vmax=vmax)
colormap.caption = '추정치매환자수 밀도'

# ---------------- 클릭/선택 상태 계산 (지도가 다시 그려져도 값 유지) ----------------
prev_map_state = st.session_state.get("seoul_map")
clicked_gu = None
if prev_map_state and prev_map_state.get('last_object_clicked_tooltip'):
    clicked_gu = prev_map_state['last_object_clicked_tooltip'].strip()

if clicked_gu:
    st.session_state['persisted_clicked_gu'] = clicked_gu
persisted_gu = st.session_state.get('persisted_clicked_gu')

final_gu = (
    selected_gu_sidebar if selected_gu_sidebar != '전체'
    else (persisted_gu if persisted_gu else None)
)

centers = df_center[df_center['시군구명'] == final_gu] if final_gu else pd.DataFrame()

# ---------------- 지도 초기화 (흰 배경, 서울 자치구만 표시) ----------------
m = folium.Map(
    location=[37.5665, 126.9780],
    tiles=None,
    zoom_control=False,
    scrollWheelZoom=False,
    dragging=False,
    doubleClickZoom=False,
    touchZoom=False,
    keyboard=False
)

m.get_root().html.add_child(folium.Element(
    "<style>.leaflet-container{background:#ffffff !important;}</style>"
))

def style_function(feature):
    gu = feature['properties']['name']
    val = patient_dict.get(gu, 0)
    is_selected = (gu == final_gu)
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

all_lats, all_lons = [], []
for feature in seoul_geo['features']:
    poly = shape(feature['geometry'])
    minx, miny, maxx, maxy = poly.bounds
    all_lons.extend([minx, maxx])
    all_lats.extend([miny, maxy])
sw = [min(all_lats), min(all_lons)]
ne = [max(all_lats), max(all_lons)]
m.fit_bounds([sw, ne], padding=(10, 10))

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

# ---------------- 선택된 자치구의 치매안심센터 마커 전부 표시 ----------------
if final_gu and not centers.empty:
    for _, crow in centers.iterrows():
        folium.Marker(
            location=[crow['위도'], crow['경도']],
            popup=crow['치매센터명'],
            tooltip=f"📍 {crow['치매센터명']}",
            icon=folium.Icon(color='red', icon='plus-sign')
        ).add_to(m)
        folium.CircleMarker(
            location=[crow['위도'], crow['경도']],
            radius=16,
            color='#e6194B',
            weight=2,
            fill=False
        ).add_to(m)

# 왼쪽 하단 범례
n_bins = 4
bin_edges = np.linspace(vmin, vmax, n_bins + 1)
legend_items_html = ""
for i in range(n_bins):
    low, high = bin_edges[i], bin_edges[i + 1]
    mid_val = (low + high) / 2
    color = colormap(mid_val)
    label = f"{low:,.0f}명 이상" if i == n_bins - 1 else f"{low:,.0f} ~ {high:,.0f}명"
    legend_items_html += f'''
    <div style="display:flex; align-items:center; gap:8px; margin-top:4px;">
        <span style="display:inline-block; width:16px; height:16px; border-radius:3px;
                     background:{color}; border:1px solid #ccc;"></span>
        <span style="font-size:11px; color:#333;">{label}</span>
    </div>
    '''
legend_html_bottomleft = f'''
<div style="position: absolute; bottom: 10px; left: 10px; z-index:9999;
            background-color:white; padding:10px 14px; border:1px solid #ddd; border-radius:8px;
            box-shadow:0 2px 6px rgba(0,0,0,0.15); font-size:12px;">
    <div style="font-weight:bold; margin-bottom:6px;">추정치매환자수 밀도</div>
    {legend_items_html}
</div>
'''
m.get_root().html.add_child(folium.Element(legend_html_bottomleft))

# ---------------- 헤더 + 범례 ----------------
legend_col1, legend_col2 = st.columns([2, 1])
with legend_col1:
    st.subheader("💪자치구별 치매환자 지원인력 현황")
with legend_col2:
    st.markdown(
        """
        <div style="display: flex; gap: 15px; justify-content: flex-end; align-items: center; padding-top: 10px;">
            <div style="display: flex; align-items: center; gap: 6px;">
                <span style="display: inline-block; width: 14px; height: 14px; background: linear-gradient(90deg, #e0f7f5, #1a3636); border-radius: 3px;"></span>
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

# ---------------- 2단 레이아웃: 왼쪽 지도, 오른쪽 상세정보 ----------------
panel_width = st.slider("오른쪽 상세정보 패널 너비 조절", min_value=20, max_value=60, value=35, step=5, format="%d%%")
left_ratio = 100 - panel_width
map_layout_left, data_layout_right = st.columns([left_ratio, panel_width])

with map_layout_left:
    # 전체 화면을 대략 1300px로 가정하고, 슬라이더 비율만큼 지도 폭을 고정 계산
    estimated_total_width = 1300
    map_width_px = int(estimated_total_width * left_ratio / 100)

    map_container = st.container(height=660)
    with map_container:
        map_data = st_folium(m, key="seoul_map", width=map_width_px, height=650)
        
with data_layout_right:
    if final_gu:
        st.markdown(f"### 📍 **{final_gu}** 2025 치매환자 지원 인프라 지표")

        row = df_use_total[df_use_total['시군구'] == final_gu]
        if not row.empty:
            r = row.iloc[0]
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

        st.markdown("🧑‍⚕️ **지정 자치구 의료 인력 현황**")

        if not centers.empty:
            total_doc = centers['의사인원수'].sum()
            total_nurse = centers['간호사인원수'].sum()
            total_social = centers['사회복지사인원수'].sum()

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

            st.write("")
            st.caption(f"🏢 관내 등록 치매안심센터 세부 인력 ({len(centers)}개, 지도에 📍로 표시됨)")
            display_df = (
                centers.set_index('치매센터명')[['의사인원수', '간호사인원수', '사회복지사인원수']]
                .T
            )
            st.dataframe(display_df, use_container_width=True)
        else:
            st.info("이 구에는 등록된 치매안심센터 정보가 없어요.")

        if final_gu in overlap_any:
            st.error(f"⚠️ **{final_gu}**는 치매 환자수에 비해 **{'·'.join(gu_reasons[final_gu])}** 인력이 현저히 부족합니다.")

        if final_gu == '성북구':
            st.warning("ℹ️ 성북구는 본소·분소의 인력 수치가 원본 데이터상 동일하게 등록되어 있어, 중복 입력 여부를 확인해야 합니다. 위 합계는 원본 데이터를 그대로 합산한 값입니다.")

    else:
        st.markdown(
            """
            <div style="border: 2px dashed #444; border-radius: 10px; padding: 40px 20px; text-align: center; margin-top: 50px;">
                <p style="font-size: 40px; margin: 0;">🖱️</p>
                <h4 style="color: #bbb; margin-top: 15px;">자치구를 클릭해 보세요!</h4>
                <p style="font-size: 13px; color: #777; margin: 5px 0 0 0;">지도에서 보고 싶은 자치구를 클릭하면 실시간 상세 정보와 센터 위치가 이 영역과 지도에 함께 표시됩니다.</p>
            </div>
            """,
            unsafe_allow_html=True
        )

st.markdown("---")
st.subheader("📊 치매안심센터 인력 상위 4 / 하위 4 자치구")

df_rank = df_center_agg.copy()
df_rank['총인원수'] = df_rank['의사인원수'] + df_rank['간호사인원수'] + df_rank['사회복지사인원수']

def build_rank_table(df_sub, start_rank):
    out = df_sub[['시군구명', '총인원수', '의사인원수', '간호사인원수', '사회복지사인원수']].copy()
    out.insert(0, '순위', range(start_rank, start_rank + len(out)))
    return out.set_index('순위')

# 상위 4개: 총인원수 → 의사수 → 간호사수 → 사회복지사수 모두 많은 순
top4_sorted = df_rank.sort_values(
    by=['총인원수', '의사인원수', '간호사인원수', '사회복지사인원수'],
    ascending=[False, False, False, False]
).reset_index(drop=True)
top4 = build_rank_table(top4_sorted.head(4), start_rank=1)

# 하위 4개: 총인원수 → 의사수 → 간호사수 → 사회복지사수 모두 적은 순
bottom4_sorted = df_rank.sort_values(
    by=['총인원수', '의사인원수', '간호사인원수', '사회복지사인원수'],
    ascending=[True, True, True, True]
).reset_index(drop=True)
bottom4_raw = bottom4_sorted.head(4)

n_total = len(df_rank)
bottom4 = build_rank_table(bottom4_raw, start_rank=n_total - 3)

rank_col1, rank_col2 = st.columns(2)
with rank_col1:
    st.markdown("**🔼 총인원수 상위 4개 구**")
    st.dataframe(top4, use_container_width=True)
with rank_col2:
    st.markdown("**🔽 총인원수 하위 4개 구**")
    st.dataframe(bottom4, use_container_width=True)

if '성북구' in top4['시군구명'].values or '성북구' in bottom4['시군구명'].values:
    st.caption("※ 성북구는 본소·분소 인력 수치가 원본 데이터상 동일하게 등록되어 있어, 중복 입력 여부가 의심됩니다. 순위는 원본 합산값 기준입니다.")

st.markdown("---")
st.subheader("🏆 인력별 최다 배치 자치구")

top1_doc = df_center_agg.sort_values('의사인원수', ascending=False).iloc[0]
top1_nurse = df_center_agg.sort_values('간호사인원수', ascending=False).iloc[0]
top1_social = df_center_agg.sort_values('사회복지사인원수', ascending=False).iloc[0]

col_doc, col_nurse, col_social = st.columns(3)

with col_doc:
    st.markdown(
        f"""
        <div style="background-color:#f3e5f5; padding:18px; border-radius:10px; text-align:center;">
            <p style="margin:0; font-size:13px; color:#7b1fa2;">👨‍⚕️ 의사 최다 배치</p>
            <h2 style="margin:8px 0 0 0; color:#4a148c;">{top1_doc['시군구명']}</h2>
            <p style="margin:5px 0 0 0; font-size:14px; color:#555;">의사 {top1_doc['의사인원수']:,.0f}명</p>
        </div>
        """,
        unsafe_allow_html=True
    )

with col_nurse:
    st.markdown(
        f"""
        <div style="background-color:#e8f5e9; padding:18px; border-radius:10px; text-align:center;">
            <p style="margin:0; font-size:13px; color:#2e7d32;">👩‍⚕️ 간호사 최다 배치</p>
            <h2 style="margin:8px 0 0 0; color:#1b5e20;">{top1_nurse['시군구명']}</h2>
            <p style="margin:5px 0 0 0; font-size:14px; color:#555;">간호사 {top1_nurse['간호사인원수']:,.0f}명</p>
        </div>
        """,
        unsafe_allow_html=True
    )

with col_social:
    st.markdown(
        f"""
        <div style="background-color:#fff3e0; padding:18px; border-radius:10px; text-align:center;">
            <p style="margin:0; font-size:13px; color:#e65100;">🧑‍🤝‍🧑 사회복지사 최다 배치</p>
            <h2 style="margin:8px 0 0 0; color:#bf360c;">{top1_social['시군구명']}</h2>
            <p style="margin:5px 0 0 0; font-size:14px; color:#555;">사회복지사 {top1_social['사회복지사인원수']:,.0f}명</p>
        </div>
        """,
        unsafe_allow_html=True
    )

st.markdown("---")
st.subheader("🔻 인력별 최소 배치 자치구")

def get_min_gu_list(col_name):
    min_val = df_center_agg[col_name].min()
    gu_list = df_center_agg[df_center_agg[col_name] == min_val]['시군구명'].tolist()
    return min_val, gu_list

min_doc_val, min_doc_gu = get_min_gu_list('의사인원수')
min_nurse_val, min_nurse_gu = get_min_gu_list('간호사인원수')
min_social_val, min_social_gu = get_min_gu_list('사회복지사인원수')

col_doc2, col_nurse2, col_social2 = st.columns(3)

with col_doc2:
    gu_text = ', '.join(min_doc_gu)
    st.markdown(
        f"""
        <div style="background-color:#f3e5f5; padding:18px; border-radius:10px; text-align:center; border:2px dashed #9c27b0;">
            <p style="margin:0; font-size:13px; color:#7b1fa2;">👨‍⚕️ 의사 최소 배치 ({len(min_doc_gu)}개 구)</p>
            <h3 style="margin:8px 0 0 0; color:#4a148c;">{gu_text}</h3>
            <p style="margin:5px 0 0 0; font-size:14px; color:#555;">의사 {min_doc_val:,.0f}명</p>
        </div>
        """,
        unsafe_allow_html=True
    )

with col_nurse2:
    gu_text = ', '.join(min_nurse_gu)
    st.markdown(
        f"""
        <div style="background-color:#e8f5e9; padding:18px; border-radius:10px; text-align:center; border:2px dashed #4caf50;">
            <p style="margin:0; font-size:13px; color:#2e7d32;">👩‍⚕️ 간호사 최소 배치 ({len(min_nurse_gu)}개 구)</p>
            <h3 style="margin:8px 0 0 0; color:#1b5e20;">{gu_text}</h3>
            <p style="margin:5px 0 0 0; font-size:14px; color:#555;">간호사 {min_nurse_val:,.0f}명</p>
        </div>
        """,
        unsafe_allow_html=True
    )

with col_social2:
    gu_text = ', '.join(min_social_gu)
    st.markdown(
        f"""
        <div style="background-color:#fff3e0; padding:18px; border-radius:10px; text-align:center; border:2px dashed #ff9800;">
            <p style="margin:0; font-size:13px; color:#e65100;">🧑‍🤝‍🧑 사회복지사 최소 배치 ({len(min_social_gu)}개 구)</p>
            <h3 style="margin:8px 0 0 0; color:#bf360c;">{gu_text}</h3>
            <p style="margin:5px 0 0 0; font-size:14px; color:#555;">사회복지사 {min_social_val:,.0f}명</p>
        </div>
        """,
        unsafe_allow_html=True
    )
