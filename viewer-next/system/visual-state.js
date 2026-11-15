"use strict";
// 地理図形の表示選択だけ。世界状態・版・時刻を設定するAPIを持たない。
globalThis.HS_VISUAL_STATE = class {
  #primary = 'globe'; #selected = new Set(['観測']);
  #layers = ['観測','推定','世界内部状態','物理的変化'];
  // 表示上の対象範囲。世界の空間台帳・取得済み範囲を意味しない。
  #spaceLabels = ['陸上','海面','水中','大気','地下','地質','宇宙'];
  #spaces = new Set(['陸上','海面','水中','大気','地下','地質','宇宙']);
  setPrimary(value) {
    if (!['globe','map'].includes(value)) throw new Error('表示種別が不正です');
    this.#primary = value;
  }
  togglePrimary() { this.#primary = this.#primary === 'globe' ? 'map' : 'globe'; }
  setLayer(layer, selected) {
    if (!this.#layers.includes(layer) || typeof selected !== 'boolean') throw new Error('表示レイヤーが不正です');
    if (selected) this.#selected.add(layer); else this.#selected.delete(layer);
  }
  setSpace(space, selected) {
    if (!this.#spaceLabels.includes(space) || typeof selected !== 'boolean') throw new Error('表示対象空間が不正です');
    if (selected) this.#spaces.add(space); else this.#spaces.delete(space);
  }
  snapshot() {
    return {primary:this.#primary,worldVersion:{value:null,unknown_reason:'基準世界版は未確定'},
      referenceTime:{value:null,unknown_reason:'基準時点・観測締切は未確定'},
      layers:this.#layers.filter(layer => this.#selected.has(layer)),
      spaces:this.#spaceLabels.filter(space => this.#spaces.has(space)),spacesAcquired:false,
      geographyAcquired:false,worldIdentityVerified:false,worldStateUpdated:false};
  }
};
