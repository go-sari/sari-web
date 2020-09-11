import moment from 'moment';
import 'bootstrap';
import bootbox from 'bootbox';

if (session_timeout) {
    let session_timer = null

    $(document).ready(function () {
        session_timer = setInterval(function () {
            let secs_left = Math.max(Math.round(session_timeout - (new Date().getTime() / 1000)), 0);
            let time_left = moment.unix(secs_left).utc();
            $("#session_timeout").text(time_left.format("HH:mm:ss"));
            if (secs_left === 0) {
                clearInterval(session_timer)
                bootbox.dialog({
                    title: "Session Timeout",
                    message: "You can now close this window!",
                    centerVertical: true,
                    onEscape: false,
                    closeButton: false
                })
            }
        }, 1000)
    })
}
