import moment from 'moment';

import "./jquery_ext";

if (session_timeout) {
    let session_timer = null

    $(document).ready(function () {
        session_timer = setInterval(function () {
            let secs_left = Math.max(Math.round(session_timeout - (new Date().getTime() / 1000)), 0);
            let time_left = moment.unix(secs_left).utc();
            $("#session_timeout").text(time_left.format("HH:mm:ss"));
            if (secs_left === 0) {
                $.redirectPost("/farewell", {
                    header1: "Session Timeout",
                    emoji: "see-ya"
                })
            }
        })
    })
}
