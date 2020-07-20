import "./style.css";

import ClipboardJS from 'clipboard';
import axios from "axios";
import moment from 'moment';

import "../jquery_ext"
import "../session"
import path from "path";

let databases = null;
let pwd_expires_msec = null;
let pwd_expire_instant = null;
let pwd_expire_timer = null;
let spinnerModal = $('#spinnerModal')

let clipboard = new ClipboardJS('.btn');
clipboard.on("success", function (e) {
    e.clearSelection();
})

$(document).ready(function () {
    setup_pwd_progress_bar();
    load_databases();
})

$("#region").change(function () {
    fill_select_picker("#db_id", Object.keys(databases[$("#region").val()]["instances"]).sort());
})

$("#db_id").change(function () {
    fill_select_picker("#sel_db_name", databases[$("#region").val()]["instances"][$("#db_id").val()].sort());
    clear_db_parameters();
})

$("#sel_db_name").change(function () {
    let db_name = $("#db_name")
    if (db_name.val() !== "") {
        db_name.val($("#sel_db_name").val())
    }
})

$("#rds_password").change(function () {
    if (pwd_expire_timer != null) {
        clearInterval(pwd_expire_timer);
        pwd_expire_timer = null;
    }
    let that = this;
    let pb = $("#pwd_progress_bar");
    if (that.value === "") {
        pb.css("width", "0%");
        return;
    }
    pb.css("width", "100%");
    let amz_props = stsTokenAmzProperties(that.value)
    pwd_expires_msec = amz_props["X-Amz-Expires"] * 1000;
    pwd_expire_instant = moment(amz_props["X-Amz-Date"]).add(pwd_expires_msec, "milliseconds").valueOf()
    pwd_expire_timer = setInterval(function () {
        let percent = 100 * (pwd_expire_instant - moment().valueOf()) / pwd_expires_msec;
        if (percent <= 0) {
            $("#rds_password").val('').change();
        } else {
            $("#pwd_progress_bar").css("width", percent + "%");
        }
    }, 1000)
})

$("#get_config").click(function () {
    let region = $("#region").val();
    let db_id = $("#db_id").val();
    let db_name = $("#sel_db_name").val();
    let url = `/api/db_config/${region}/${db_id}/${db_name}`;
    getJSON(url, function (config) {
        for (const [key, value] of Object.entries(config)) {
            $(`#${key}`).val(value).change();
        }
    })
})

function getJSON(url, success) {
    let completed = false
    spinnerModal.one('shown.bs.modal', function () {
        // modal('hide') doesn't work if the 'show' transition is still ongoing.
        // See https://github.com/twbs/bootstrap/issues/25008#issuecomment-575259382
        if (completed)
            spinnerModal.modal('hide');
    }).modal('show');
    axios.get(url)
        .then(response => success(response.data))
        .catch(error => {
            alert(error)
        })
        .finally(function () {
            completed = true
            spinnerModal.modal('hide');
        })
}

function stsTokenAmzProperties(token) {
    return Object.assign({}, ...token.split('&')
        .filter(s => s.startsWith("X-Amz-"))
        .map(s => s.split("=", 2))
        .filter(pair => pair.length === 2)
        .map(pair => ({[pair[0]]: pair[1]}))
    );
}

function setup_pwd_progress_bar() {
    let pb = $("#pwd_progress_bar")
    pb.parent().css('width', $('#rds_password').css('width'))
}

function load_databases() {
    let url = `/api/databases`
    getJSON(url, function (databases_) {
        databases = databases_;
        if ($.isEmptyObject(databases)) {
            $.redirectPost(path.resolve(applicationRoot, "farewell"), {
                header1: "Oops!",
                header2: "Sorry, but we couldn't find any RDS instance you are allowed to access on this AWS account.",
                emoji: "confused"
            })
        } else {
            fill_select_picker("#region", Object.keys(databases).sort(),
                function (id) {
                    return {
                        "value": id,
                        "text": databases[id]["location"],
                        "subtext": id
                    }
                });
        }
    })
}

function fill_select_picker(id, options, optionFactory) {
    const select = $(id);
    select.empty()
    options.forEach(function (key) {
        let option;
        if (optionFactory) {
            let data = optionFactory(key)
            option = $(`<option value="${data['value']}" data-subtext="${data['subtext']}">${data["text"]}</option>`);
        } else {
            option = $(`<option value="${key}">${key}</option>`);
        }
        select.append(option)
    });
    select.selectpicker('refresh');
    select.trigger('loaded.bs.select');
    select.change();
}

function clear_db_parameters() {
    $(".db-param").val("").change();
}
