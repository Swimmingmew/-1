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
st.sidebar.markdown("🟣 색상 진하기 : 추정치매환자수")
st.sidebar.markdown("▬▬ 점선 : 환자수 많은데 인력 부족한 구")

patient_dict = df_use_total.set_index('시군구')['추정치매환자수'].to_dict()
vmin, vmax = min(patient_dict.values()), max(patient_dict.values())
colormap = cm.LinearColormap(colors=['#f3e5f5', '#7b1fa2', '#3a0066'], vmin=vmin, vmax=vmax)
colormap.caption = '추정치매환자수'

m = folium.Map(
    location=[37.5665, 126.9780],
    zoom_start=11,
    min_zoom=11,
    max_zoom=11,
    tiles='cartodbpositron',
    zoom_control=False,
    scrollWheelZoom=False,
    dragging=False,
    doubleClickZoom=False,
    touchZoom=False,
    keyboard=False
)

def style_function(feature):
    gu = feature['properties']['name']
    val = patient_dict.get(gu, 0)
    is_selected = (gu == selected_gu_sidebar)
    return {
        'fillColor': colormap(val),
        'color': '#333' if not is_selected else 'black',
        'weight': 1 if not is_selected else 3,
        'fillOpacity': 0.85,
    }

geo_layer = folium.GeoJson(
    seoul_geo,
    style_function=style_function,
    highlight_function=lambda x: {'weight': 3, 'color': 'black'},
    tooltip=folium.GeoJsonTooltip(fields=['name'], aliases=[''], labels=False, sticky=True),
)
geo_layer.add_to(m)
colormap.add_to(m)

# ---------------- 구별 폴리곤 중심좌표 + 이름 라벨 ----------------
gu_centroids = {}
for feature in seoul_geo['features']:
    gu_name = feature['properties']['name']
    centroid = shape(feature['geometry']).centroid
    gu_centroids[gu_name] = (centroid.y, centroid.x)

    label_html = (
        '<div style="font-size:11px;font-weight:bold;color:#222;text-align:center;'
        'text-shadow:1px 1px 2px white,-1px -1px 2px white,1px -1px 2px white,-1px 1px 2px white;">'
        + gu_name + '</div>'
    )
    folium.Marker(
        location=[centroid.y, centroid.x],
        icon=folium.DivIcon(icon_size=(80, 20), icon_anchor=(40, 10), html=label_html)
    ).add_to(m)

# ---------------- 환자수 많은데 인력 부족한 구: 점선 테두리 + 경고 라벨 (이모지 없음) ----------------
overlap_geo = {"type": "FeatureCollection",
               "features": [f for f in seoul_geo['features'] if f['properties']['name'] in overlap_any]}
folium.GeoJson(
    overlap_geo,
    style_function=lambda x: {'fillColor': 'transparent', 'color': 'black', 'weight': 4, 'dashArray': '5,5'}
).add_to(m)

for gu_name in overlap_any:
    if gu_name not in gu_centroids:
        continue
    lat, lon = gu_centroids[gu_name]
    reason_text = '·'.join(gu_reasons[gu_name]) + ' 부족'
    warn_html = (
        '<div style="background-color:black;color:white;padding:2px 5px;border-radius:4px;'
        'font-size:10px;font-weight:bold;white-space:nowrap;text-align:center;'
        'box-shadow:0 0 3px rgba(0,0,0,0.5);">'
        f'⚠ {reason_text}</div>'
    )
    folium.Marker(
        [lat + 0.011, lon],
        icon=folium.DivIcon(icon_size=(130, 24), icon_anchor=(65, 12), html=warn_html)
    ).add_to(m)

st.subheader("🗺️ 자치구별 치매현황 지도 (자치구를 클릭하면 하단에 상세정보가 표시돼요)")
map_data = st_folium(m, width=1100, height=650)

clicked_gu = None
if map_data and map_data.get('last_object_clicked_tooltip'):
    clicked_gu = map_data['last_object_clicked_tooltip'].strip()

final_gu = clicked_gu if clicked_gu else (selected_gu_sidebar if selected_gu_sidebar != '전체' else None)

st.markdown("---")
if final_gu:
    st.subheader(f"📍 {final_gu} 상세정보")
    row = df_use_total[df_use_total['시군구'] == final_gu]
    if not row.empty:
        r = row.iloc[0]
        d1, d2, d3 = st.columns(3)
        d1.metric("노인인구수", f"{r['노인인구수']:,.0f}명")
        d2.metric("추정치매환자수", f"{r['추정치매환자수']:,.0f}명")
        d3.metric("추정치매환자유병률", f"{r['추정치매환자유병률']}%")

    centers = df_center[df_center['시군구명'] == final_gu]
    if not centers.empty:
        st.write("**치매안심센터 목록**")
        st.dataframe(
            centers[['치매센터명', '의사인원수', '간호사인원수', '사회복지사인원수']],
            use_container_width=True, hide_index=True
        )
    else:
        st.info("이 구에는 등록된 치매안심센터 정보가 없어요.")
else:
    st.info("지도에서 자치구를 클릭하거나, 왼쪽에서 자치구를 선택하면 상세정보가 여기 표시돼요.")

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
