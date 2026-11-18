# Rectangular block with 8 x 4 x 2 HEXA_8 cells. Run in a fresh ICEM batch directory.
set divisions {8 4 2}
ic_geo_cre_pnt BOX corner0 {0 0 0}
ic_geo_cre_pnt BOX corner1 {8 4 2}
ic_curve points BOX diagonal {corner0 corner1}
ic_geo_new_family SOLID
ic_hex_initialize_blocking {} SOLID 0 101
for {set axis 0} {$axis < 3} {incr axis} {
    foreach i {1 2} {
        foreach j {1 2} {
            set p [list $i $j]
            set a [lindex [ic_hex_vertex_number " [linsert $p $axis 1] "] 0]
            set b [lindex [ic_hex_vertex_number " [linsert $p $axis 2] "] 0]
            ic_hex_set_mesh $a $b n [expr {1 + [lindex $divisions $axis]}] h1rel 0 h2rel 0 r1 1 r2 1 lmax 0 default unlocked
        }
    }
}
ic_hex_save_blocking cube.blk
ic_hex_write_file cube.uns SOLID proj 0 dim_to_mesh 3 -family_boco cube.fbc
ic_uns_load cube.uns 3 0 {} 2
set n [ic_count_elements hexa]
set stats [ic_uns_subset_metric SOLID HEXA_8 Determinant 1]
if {$n != 64 || [lindex $stats 0] != $n || [lindex $stats 3] < 0.99} {
    error "Expected 64 regular hexahedra; actual $n; determinant statistics: $stats"
}
set out [open mesh.csv w]
puts $out "metric,unit,value"
puts $out "hexahedra,count,$n"
puts $out "determinant,1,[lindex $stats 3]"
close $out
