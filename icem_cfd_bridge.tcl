# ANSYS ICEM CFD MCP bridge
#
# Start with:
#   icemcfd.bat -script icem_cfd_bridge.tcl
# or, for a headless persistent session:
#   icemcfd.bat -batch -script icem_cfd_bridge.tcl
#
# The Python MCP server writes small Tcl descriptors to commands/. This bridge
# evaluates their referenced Tcl payloads inside the live ICEM interpreter and
# writes JSON results back to results/.

set ::icem_mcp_version "0.3.0"
set ::icem_mcp_running 1
set ::icem_mcp_command_count 0
set ::icem_mcp_last_status 0

if {[info exists ::env(ANSYS_ICEM_MCP_HOME)] && $::env(ANSYS_ICEM_MCP_HOME) ne ""} {
    set ::icem_mcp_home [file normalize $::env(ANSYS_ICEM_MCP_HOME)]
} else {
    set ::icem_mcp_home [file normalize [file join [pwd] icem]]
}

set ::icem_mcp_commands_dir [file join $::icem_mcp_home commands]
set ::icem_mcp_results_dir [file join $::icem_mcp_home results]
set ::icem_mcp_scripts_dir [file join $::icem_mcp_home scripts]
set ::icem_mcp_status_file [file join $::icem_mcp_home status.json]
set ::icem_mcp_log_file [file join $::icem_mcp_home icem_bridge.log]

file mkdir $::icem_mcp_commands_dir
file mkdir $::icem_mcp_results_dir
file mkdir $::icem_mcp_scripts_dir

proc icem_mcp_json_escape {value} {
    return [string map [list \
        "\\" "\\\\" \
        "\"" "\\\"" \
        "\b" "\\b" \
        "\f" "\\f" \
        "\n" "\\n" \
        "\r" "\\r" \
        "\t" "\\t"] $value]
}

proc icem_mcp_json_string {value} {
    return "\"[icem_mcp_json_escape $value]\""
}

proc icem_mcp_atomic_write {path content} {
    set tmp "${path}.[pid].tmp"
    set channel [open $tmp w]
    fconfigure $channel -encoding utf-8 -translation lf
    puts -nonewline $channel $content
    close $channel
    file rename -force $tmp $path
}

proc icem_mcp_read_utf8 {path} {
    set channel [open $path r]
    fconfigure $channel -encoding utf-8 -translation auto
    set content [read $channel]
    close $channel
    return $content
}

proc icem_mcp_log {message} {
    set channel [open $::icem_mcp_log_file a]
    fconfigure $channel -encoding utf-8 -translation lf
    puts $channel "[clock format [clock seconds] -format {%Y-%m-%d %H:%M:%S}] $message"
    close $channel
}

proc icem_mcp_write_status {status} {
    set json "\{"
    append json "\"status\":[icem_mcp_json_string $status],"
    append json "\"pid\":[pid],"
    append json "\"version\":[icem_mcp_json_string $::icem_mcp_version],"
    append json "\"heartbeat\":[clock seconds],"
    append json "\"command_count\":$::icem_mcp_command_count,"
    append json "\"mcp_home\":[icem_mcp_json_string $::icem_mcp_home]"
    append json "\}"
    icem_mcp_atomic_write $::icem_mcp_status_file $json
    set ::icem_mcp_last_status [clock seconds]
}

proc icem_mcp_write_result {path command_id success result error traceback elapsed} {
    set json "\{"
    append json "\"success\":[expr {$success ? "true" : "false"}],"
    append json "\"id\":[icem_mcp_json_string $command_id],"
    append json "\"elapsed_seconds\":$elapsed,"
    append json "\"result\":[icem_mcp_json_string $result],"
    append json "\"error\":[icem_mcp_json_string $error],"
    append json "\"traceback\":[icem_mcp_json_string $traceback]"
    append json "\}"
    icem_mcp_atomic_write $path $json
}

proc icem_mcp_execute_descriptor {descriptor} {
    set command_id [file rootname [file tail $descriptor]]
    if {[string match "cmd_*" $command_id]} {
        set command_id [string range $command_id 4 end]
    }
    set command_type ""
    set script_file ""
    set result_file [file join $::icem_mcp_results_dir "${command_id}.json"]
    set started [clock seconds]

    set descriptor_code [catch {eval [icem_mcp_read_utf8 $descriptor]} descriptor_result]
    catch {file delete -force $descriptor}
    if {$descriptor_code != 0} {
        set trace ""
        if {[info exists ::errorInfo]} {
            set trace $::errorInfo
        }
        icem_mcp_write_result $result_file $command_id 0 "" $descriptor_result $trace 0
        icem_mcp_log "Descriptor failed: $descriptor_result"
        return
    }

    if {$command_type eq "ping"} {
        icem_mcp_write_result $result_file $command_id 1 "pong" "" "" 0
        incr ::icem_mcp_command_count
        return
    }

    if {$command_type eq "stop"} {
        icem_mcp_write_result $result_file $command_id 1 "stopping" "" "" 0
        incr ::icem_mcp_command_count
        after 100 icem_mcp_stop
        return
    }

    if {$command_type ne "execute"} {
        icem_mcp_write_result $result_file $command_id 0 "" "Unsupported command type: $command_type" "" 0
        incr ::icem_mcp_command_count
        return
    }

    if {$script_file eq "" || ![file exists $script_file]} {
        icem_mcp_write_result $result_file $command_id 0 "" "Script file not found: $script_file" "" 0
        incr ::icem_mcp_command_count
        return
    }

    set execute_code [catch {uplevel #0 [icem_mcp_read_utf8 $script_file]} execute_result]
    set elapsed [expr {[clock seconds] - $started}]
    if {$execute_code == 0 || $execute_code == 2} {
        icem_mcp_write_result $result_file $command_id 1 $execute_result "" "" $elapsed
        icem_mcp_log "Command $command_id completed"
    } else {
        set trace ""
        if {[info exists ::errorInfo]} {
            set trace $::errorInfo
        }
        icem_mcp_write_result $result_file $command_id 0 "" $execute_result $trace $elapsed
        icem_mcp_log "Command $command_id failed: $execute_result"
    }
    incr ::icem_mcp_command_count
}

proc icem_mcp_poll {} {
    if {!$::icem_mcp_running} {
        return
    }

    foreach descriptor [lsort [glob -nocomplain -directory $::icem_mcp_commands_dir cmd_*.tcl]] {
        icem_mcp_execute_descriptor $descriptor
    }

    if {[expr {[clock seconds] - $::icem_mcp_last_status}] >= 2} {
        icem_mcp_write_status "running"
    }
    after 200 icem_mcp_poll
}

proc icem_mcp_stop {} {
    set ::icem_mcp_running 0
    icem_mcp_write_status "stopped"
    icem_mcp_log "ICEM CFD MCP bridge stopped"
    after 50 exit
}

icem_mcp_write_status "running"
icem_mcp_log "ICEM CFD MCP bridge v$::icem_mcp_version started (pid [pid])"
after 100 icem_mcp_poll

# med_batch exits when the startup script returns, so keep its Tcl event loop
# alive. In GUI mode ICEM owns the event loop after this startup script returns.
if {[info exists ::env(ICEM_MCP_BATCH)] && $::env(ICEM_MCP_BATCH) eq "1"} {
    vwait ::icem_mcp_running
}
