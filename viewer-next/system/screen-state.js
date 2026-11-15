"use strict";
// 表示タブ/絞込みだけ。入力モード・世界状態・権限を持たない。
globalThis.HS_SCREEN_STATE = class {
  #detail = '概要'; #category = 'すべて'; #region = 'すべて'; #reportDetail = null;
  setDetail(value) {
    if (!['概要','観測事実','影響分析','対応状況','関連情報'].includes(value)) throw new Error('詳細タブが不正です');
    this.#detail=value;
  }
  setCategory(value) {
    if (!['すべて','地政学','経済','自然災害','社会・制度','資源・物流','感染症'].includes(value)) throw new Error('カテゴリが不正です');
    this.#category=value;
  }
  setRegion(value) {
    if (!['すべて','アジア','ヨーロッパ','北米','南米','アフリカ','中東','オセアニア'].includes(value)) throw new Error('地域フィルタが不正です');
    this.#region=value;
  }
  clearReportFilters() {this.#category='すべて';this.#region='すべて';}
  openReportDetail() {
    this.#reportDetail={region:this.#region,category:this.#category,reportVersion:null,eventId:null,worldVersion:null,referenceTime:null,generated:false};
  }
  closeReportDetail() {this.#reportDetail=null;}
  snapshot() {return {detailTab:this.#detail,reportCategory:this.#category,reportRegion:this.#region,reportDetail:this.#reportDetail?{...this.#reportDetail}:null,dataAcquired:false,worldStateUpdated:false,executionAuthorized:false};}
};
