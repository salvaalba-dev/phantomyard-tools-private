/* Session-only consultation state; never stores credentials, history or ACL claims. */
'use strict';
const CHAT_JOBS='/api/scoped-assistant/jobs';
const chatUUID=value=>typeof value==='string'&&/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(value);
const chatProtocolError=()=>Object.assign(Error('Current scoped consultation required'),{status:409});
class ScopedChat {
  constructor({request,render,onInvalid,delay=()=>new Promise(resolve=>setTimeout(resolve,1000)),uuid=()=>crypto.randomUUID()}) {
    Object.assign(this,{request,render,onInvalid,delay,uuid});this.epoch=0;this.view=null;this.info=null;
    this.job=null;this.retryBody=null;this.focus=null;this.busy=false;this.state={status:'unavailable',text:'',question:''};
  }
  emit(status,text='',question='') {
    this.state={status,text,question};this.render({...this.state,busy:this.busy,retry:!!this.retryBody,
      persona:this.info?.persona||'',focus:this.focus?.title||'',available:!!this.view});
  }
  async discard(id) {try{await this.request('DELETE',CHAT_JOBS+'/'+id);}catch{/* Best effort; server expiry remains enforced. */}}
  reset(disable=true) {
    this.epoch++;if(this.job)this.discard(this.job);this.job=null;this.retryBody=null;this.focus=null;this.busy=false;
    if(disable){this.view=null;this.info=null;}this.emit(this.view?'ready':'unavailable');
  }
  enable(info,view) {
    this.reset();
    if(info?.available!==true||typeof info.persona!=='string'||!info.persona||info.scope_id!==view.scope_id
        ||typeof view.view_revision!=='string'||!/^[a-f0-9]{64}$/.test(view.view_revision))return;
    this.info={persona:info.persona};this.view={scope_id:view.scope_id,view_revision:view.view_revision};this.emit('ready');
  }
  setFocus(record) {
    if(!this.view)return;this.reset(false);
    if(record){if(!/^[a-f0-9]{64}$/.test(record.id))throw Error('Invalid visible focus');this.focus={id:record.id,title:String(record.title).slice(0,120)};}
    this.emit('ready');
  }
  cancel(){this.reset(false);this.emit('cancelled');}
  async send(question,retry=false) {
    if(!this.view||this.busy||(!retry&&this.retryBody))return;
    if(typeof question!=='string'||!question.trim()||[...question].length>1800)return;
    const body=retry?this.retryBody:{request_id:this.uuid(),question:question.trim(),resource_ids:this.focus?[this.focus.id]:[]};
    if(!body)return;
    if(!retry&&this.job){this.discard(this.job);this.job=null;}
    const ticket=++this.epoch;this.busy=true;this.retryBody=null;this.emit('submitting','',body.question);
    try {
      let job=await this.request('POST',CHAT_JOBS,body);
      if(!chatUUID(job?.id))throw chatProtocolError();
      if(ticket!==this.epoch){await this.discard(job.id);return;}
      this.job=job.id;
      for(let attempts=0;attempts<150;attempts++) {
        if(ticket!==this.epoch)return;
        if(!job||job.id!==this.job||!['queued','running','complete','held','failed','cancelled'].includes(job.status))throw chatProtocolError();
        if(!['queued','running'].includes(job.status)) {
          let answer='';
          if(job.status==='complete') {
            const result=job.result;
            if(!result||result.status!=='complete'||result.request_id!==body.request_id||result.complete_corpus!==false
                ||result.persona!==this.info.persona||result.scope_id!==this.view.scope_id||result.view_revision!==this.view.view_revision
                ||typeof result.text!=='string'||new TextEncoder().encode(result.text).length>64000)throw chatProtocolError();
            answer=result.text;
          }
          this.busy=false;this.emit(job.status,answer,body.question);return;
        }
        this.emit(job.status,'',body.question);await this.delay();if(ticket!==this.epoch)return;
        job=await this.request('GET',CHAT_JOBS+'/'+this.job);
      }
      await this.discard(this.job);throw Error('Consultation deadline exceeded');
    } catch(error) {
      if(ticket!==this.epoch)return;
      this.busy=false;
      if([401,403,404,409].includes(error.status)){this.reset();this.onInvalid();return;}
      this.retryBody=body;this.emit(error.status===429?'limited':'error','',body.question);
    }
  }
}
if(typeof module!=='undefined'&&module.exports)module.exports={ScopedChat};
