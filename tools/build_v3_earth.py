"""Deterministic geographic backdrop, unrelated to synthetic state locations.

Natural Earth 1:110m public-domain land; orthographic dots at fixed 1.5° grid.
Not a measured world metric, network, country assignment or animation.
"""
import json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def inside(x,y,ring):
    yes=False
    for (a,b),(c,d) in zip(ring,ring[1:]+ring[:1]):
        if (b>y)!=(d>y) and x<(c-a)*(y-b)/(d-b)+a:yes=not yes
    return yes

def build():
    data=json.loads((ROOT/'ui/v3/vendor/ne_110m_land.geojson').read_text())
    polygons=[]
    for feature in data['features']:
        g=feature['geometry']; polys=g['coordinates'] if g['type']=='MultiPolygon' else [g['coordinates']]
        for poly in polys:
            ring=poly[0];polygons.append((min(x for x,y in ring),max(x for x,y in ring),min(y for x,y in ring),max(y for x,y in ring),poly))
    circles=[];phi0=math.radians(18);lon0=math.radians(48)
    for yi in range(-59,60):
        lat=yi*1.5;phi=math.radians(lat)
        for xi in range(-120,120):
            lon=xi*1.5;lam=math.radians(lon)-lon0
            z=math.sin(phi0)*math.sin(phi)+math.cos(phi0)*math.cos(phi)*math.cos(lam)
            if z<=0:continue
            if not any(lo<=lon<=hi and bot<=lat<=top and inside(lon,lat,poly[0]) and not any(inside(lon,lat,h) for h in poly[1:]) for lo,hi,bot,top,poly in polygons):continue
            x=260+232*math.cos(phi)*math.sin(lam)
            y=260-232*(math.cos(phi0)*math.sin(phi)-math.sin(phi0)*math.cos(phi)*math.cos(lam))
            circles.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{.55+z*.85:.2f}" opacity="{.35+z*.6:.2f}"/>')
    svg='''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 520" role="img" aria-label="地球の地形。合成国家の地理的位置は示さない。"><defs>
<radialGradient id="sea" cx="34%" cy="28%" r="78%"><stop stop-color="#174553"/><stop offset=".45" stop-color="#09202c"/><stop offset="1" stop-color="#02070f"/></radialGradient>
<radialGradient id="shade" cx="25%" cy="20%" r="90%"><stop offset=".3" stop-color="#010813" stop-opacity="0"/><stop offset="1" stop-color="#01050a" stop-opacity=".94"/></radialGradient>
<linearGradient id="rim" x2="1" y2="1"><stop stop-color="#b4f8ff" stop-opacity=".7"/><stop offset=".45" stop-color="#65dcea" stop-opacity=".3"/><stop offset="1" stop-color="#326674" stop-opacity=".2"/></linearGradient>
<filter id="halo"><feGaussianBlur stdDeviation="6"/></filter></defs>
<circle cx="260" cy="260" r="234" fill="none" stroke="#68d5e9" stroke-opacity=".25" stroke-width="5" filter="url(#halo)"/>
<circle cx="260" cy="260" r="232" fill="url(#sea)"/>
<g fill="#9be1dd">'''+''.join(circles)+'''</g>
<circle cx="260" cy="260" r="232" fill="url(#shade)"/>
<circle cx="260" cy="260" r="233" fill="none" stroke="url(#rim)" stroke-width="1.2"/>
</svg>'''
    (ROOT/'ui/v3/earth.svg').write_text(svg,encoding='utf-8')
    print('V3 Earth backdrop built; no synthetic geography or routes')
if __name__=='__main__':build()
