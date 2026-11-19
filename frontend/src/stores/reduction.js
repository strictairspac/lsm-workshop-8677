import{list}from'../api/reduction.js';export const reductions={items:[],async load(){this.items=await list();return this.items}};
