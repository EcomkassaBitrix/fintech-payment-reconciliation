ALTER TABLE t_p83864310_fintech_payment_reco.platform_settings ADD COLUMN IF NOT EXISTS metrika_script TEXT NULL;
UPDATE t_p83864310_fintech_payment_reco.platform_settings SET metrika_counter_id = '113249997', metrika_script = '<!-- Yandex.Metrika counter -->
<script type="text/javascript">
    (function(m,e,t,r,i,k,a){
        m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
        m[i].l=1*new Date();
        for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
        k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)
    })(window, document,''script'',''https://mc.yandex.ru/metrika/tag.js?id=113249997'', ''ym'');

    ym(113249997, ''init'', {ssr:true, webvisor:true, clickmap:true, ecommerce:"dataLayer", referrer: document.referrer, url: location.href, accurateTrackBounce:true, trackLinks:true});
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/113249997" style="position:absolute; left:-9999px;" alt="" /></div></noscript>
<!-- /Yandex.Metrika counter -->' WHERE id = 1;